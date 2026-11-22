# Đặt tiêu chí hoàn tất refactor legacy cast sang pattern matching (Java 21)

## 1. Vì sao cần tiêu chí hoàn tất rõ ràng?

Khi refactor mã Java cũ từ cách kiểm tra kiểu rồi ép kiểu thủ công sang **pattern matching**, thay đổi nhìn có vẻ rất nhỏ:

```java
// Trước
if (value instanceof String) {
    String text = (String) value;
    return text.trim();
}

// Sau
if (value instanceof String text) {
    return text.trim();
}
```

Nhưng "**biên dịch thành công**" chưa đủ để khẳng định refactor hoàn tất. Một thay đổi trong thứ tự nhánh, xử lý `null`, exception, phương thức accessor hoặc side effect có thể làm **hành vi quan sát được thay đổi**, dù cú pháp mới ngắn hơn.

**Tiêu chí hoàn tất (Definition of Done, DoD)** là tập điều kiện **có thể kiểm chứng** trước khi chấp nhận thay đổi. Trong chủ đề *Refactor legacy cast*, DoD nên trả lời năm câu hỏi:

1. **Đã thay đúng phần nào?** Phạm vi, API và luồng dữ liệu có được ghi rõ không?
2. **Mã mới có giữ đúng hợp đồng hành vi không?** Đầu ra, `null`, exception, thứ tự kiểm tra, side effect và tính tương thích đều được xét.
3. **Có bằng chứng kiểm thử không?** Test biên, test hồi quy, phép so sánh trước–sau và môi trường chạy được xác nhận.
4. **Có đáp ứng chuẩn chất lượng của dự án không?** Java version, compiler, static analysis, review và CI.
5. **Nếu rủi ro xảy ra thì làm gì?** Các thay đổi có chủ ý được phê duyệt, có khả năng theo dõi và rollback.

**Phiên bản:** Pattern matching cho `instanceof` chuẩn từ Java 16 (JEP 394); record patterns (JEP 440) và pattern matching cho `switch` (JEP 441) chuẩn từ **Java 21**. Khi dùng record hoặc `switch` patterns như ví dụ trong bài, đặt mục tiêu JDK 21+; không cần bật preview.

## 2. Xác định phạm vi và hành vi gốc trước khi sửa

Trước khi thay cast, cần xác định **đâu là hành vi cần bảo toàn**. Không nên vừa đổi cú pháp vừa thay đổi quy tắc nghiệp vụ mà không ghi rõ.

### 2.1. Phân loại mã legacy

| Mẫu mã cũ | Hướng refactor | Điều cần chứng minh |
| --- | --- | --- |
| `if (o instanceof String) { String s = (String) o; ... }` | `if (o instanceof String s) { ... }` | Kiểu match, kết quả và phạm vi biến giống trước |
| `if (!(o instanceof String)) return ...; String s = (String) o;` | `if (!(o instanceof String s)) return ...; ...` | Biến `s` chỉ dùng sau đường đi đã match |
| Chuỗi `if/else if` theo nhiều subtype | Type patterns hoặc pattern `switch` | Giữ ưu tiên nhánh cụ thể và hành vi `null` |
| Dùng `(String) o` trực tiếp, không có `instanceof` | **Không thay máy móc** | Cân nhắc `ClassCastException`, `NullPointerException` và hợp đồng API |
| Cast record rồi đọc một hoặc nhiều component | Type pattern, đôi khi record pattern | Không vô tình gọi accessor khác/thêm lần |
| Generic cast unchecked như `(List<String>) o` | Kiểm tra/đổi thiết kế kiểu phù hợp | Pattern không thể xác minh generic element type bị xóa ở runtime |

**Scope** nên ghi: tệp/phương thức được sửa, dạng cast thuộc phạm vi, nhánh được giữ nguyên, nơi gọi ảnh hưởng, phiên bản Java đích và những thay đổi nghiệp vụ **không** thuộc cùng PR.

### 2.2. Tạo baseline có thể so sánh

Lưu bằng chứng trước khi sửa: commit hoặc revision làm mốc, các test hiện có, kết quả thực thi của những ca đại diện, hợp đồng công khai, cách ghi log và exception quan trọng. Với logic có hiệu năng hoặc side effect, ghi thêm các chỉ số phù hợp trước khi sửa.

Không được suy ra "không thay đổi hành vi" chỉ từ việc hai đoạn mã trông tương đương. **Hợp đồng hành vi** có thể gồm:

- Giá trị trả về và kiểu dữ liệu của kết quả.
- Độ ưu tiên giữa các loại đối tượng, nhất là subtype và interface.
- Xử lý `null`, chuỗi blank, số âm, collection rỗng hoặc component `null`.
- Loại exception và điều kiện ném exception mà caller đang phụ thuộc.
- Số lần gọi accessor, thứ tự side effect, thao tác sửa dữ liệu, I/O.
- Tính tương thích source/binary và yêu cầu runtime của hệ thống.

Nếu một hành vi cũ vốn là bug cần sửa, **đánh dấu đó là thay đổi có chủ ý** và yêu cầu test/duyệt riêng; không gộp nó vào nhóm "refactor thuần túy".

## 3. Bộ tiêu chí hoàn tất có thể kiểm chứng

Bảng sau là khung DoD cho một PR chuyển legacy casts sang Java patterns. Mỗi mục cần **evidence**, không chỉ câu trả lời "đã làm".

| Nhóm | Tiêu chí chấp nhận | Bằng chứng gợi ý |
| --- | --- | --- |
| **Phạm vi** | Chỉ đổi các cast đã xác định; không đổi API hoặc nghiệp vụ ngoài phạm vi | Diff PR, danh sách method/call sites |
| **Cú pháp & tương thích** | Mã biên dịch bằng mức Java đích (ví dụ `--release 21`); không dùng preview ngoài yêu cầu | Lệnh build, log CI, JDK version |
| **An toàn kiểu** | Không còn cast dư thừa ở các nhánh đã chuyển; không thêm unchecked/raw cast để "lách" compiler | Review diff và compiler/static analysis |
| **Hành vi** | Đầu ra và nhánh chọn giống baseline cho các loại đầu vào được chấp nhận | Regression tests, differential tests |
| **Null và ngoại lệ** | Mọi trường hợp `null`/wrong type giữ hợp đồng, hoặc thay đổi được duyệt riêng | Test `null`, `ClassCastException`, `NullPointerException` |
| **Pattern scope** | Biến pattern chỉ dùng ở đường đi chắc chắn match; `&&`/`||` đúng short-circuit | Compiler và test điều kiện |
| **Thứ tự/coverage nhánh** | Không có case bị dominated; các `switch` expressions exhaustive; không vô tình bỏ nhánh | Compiler, tests các subtype |
| **Side effect** | Số lần/ thứ tự đọc accessor, sửa collection, log, I/O không đổi ngoài chủ ý | Unit tests, mock/counter/fake |
| **Chất lượng** | Test dự án, lint/static analysis, review và các chính sách CI bắt buộc đạt | CI status, review approval |
| **Khả năng triển khai** | Có kế hoạch giám sát, rollback phù hợp với mức độ rủi ro | PR notes, release checklist |

Một tiêu chí chỉ được đánh dấu **PASS** khi cả cách xác minh và kết quả đều rõ ràng. Không nhất thiết mọi dự án phải dùng cùng chỉ số coverage/benchmark; ngưỡng cần phù hợp chính sách hiện có và mức độ rủi ro thực tế.

## 4. Không đổi hành vi: các cạm bẫy quan trọng

### 4.1. `instanceof` có thể không thay thế cast trực tiếp

Xét đoạn cũ:

```java
static int strictCast(Object input) {
    return ((String) input).length();
}
```

Khi `input` là `Integer`, cast ném `ClassCastException`. Khi `input == null`, cast về `String` thành công (vẫn `null`), nhưng lời gọi `length()` ném `NullPointerException`.

Nếu thay bằng:

```java
static int changedSemantics(Object input) {
    return input instanceof String text ? text.length() : -1;
}
```

thì `Integer` **và** `null` đều trả `-1`. Đây là một **thay đổi hành vi quan sát được**, không còn là refactor thuần túy. Không được coi nó là hoàn tất nếu hợp đồng cũ yêu cầu ném exception hoặc caller đang dựa vào exception đó.

**Tiêu chí DoD:** Với cast trực tiếp, phải ghi rõ trạng thái: giữ nguyên hành vi cũ; hoặc thay đổi có chủ ý được phê duyệt và có test mới. Đừng tạo giả ngoại lệ chỉ để làm test xanh mà không hiểu hợp đồng.

### 4.2. `null` và nhánh `switch`

Với chuỗi `if/else if` dùng `instanceof`, một selector `null` thường đi qua các nhánh và rơi vào fallback. Khi chuyển sang pattern `switch`, **`null` không tự rơi vào `default`**; nếu muốn giữ fallback cũ, cần `case null -> ...` phù hợp:

```java
return switch (input) {
    case String text -> "text:" + text;
    case Integer number -> "int:" + number;
    case null -> "other";
    default -> "other";
};
```

Nếu cố tình chọn ném `NullPointerException` cho `null`, đó là quyết định API phải được ghi nhận, không nên xảy ra ngẫu nhiên do đổi hình thức kiểm soát luồng.

### 4.3. Thứ tự subtype và dominance

Mã cũ thường ưu tiên subtype:

```java
if (input instanceof String) {
    return "string";
}
if (input instanceof CharSequence) {
    return "sequence";
}
return "other";
```

Khi đổi sang `switch` phải giữ `String` đứng trước `CharSequence`:

```java
return switch (input) {
    case String text -> "string";
    case CharSequence chars -> "sequence";
    case null -> "other";
    default -> "other";
};
```

Nếu đảo `CharSequence` lên trên, Java 21 từ chối `case String` phía dưới vì **dominated**. Compiler giúp phát hiện một lớp lỗi, nhưng vẫn phải kiểm tra sự ưu tiên giữa các guard khác nhau vốn có thể chồng lấn.

### 4.4. Flow scoping của pattern variables

Những cách viết sau hợp lệ:

```java
if (input instanceof String text && !text.isBlank()) {
    return text.trim();
}

if (!(input instanceof String text)) {
    return "not string";
}
return text.trim();
```

Hai đoạn là **ví dụ riêng biệt trong phương thức trả `String`**, không đặt nối tiếp trong cùng một phương thức với biến `text` trùng tên. Trong ví dụ thứ nhất, vế phải `&&` chỉ chạy sau match thành công. Trong ví dụ thứ hai, nhánh sai đã `return`, nên đường đi còn lại chứng minh biến được bind.

Cách viết sau **cố ý không biên dịch**:

```java
// SAI: vế phải của || chỉ chạy khi match thất bại.
return input instanceof String text || text.isBlank();
```

**Tiêu chí DoD:** Biến pattern không bị dùng ngoài đường đi đã match; điều kiện kết hợp giữ đúng logic `&&`, `||` và dấu `!`.

### 4.5. Record deconstruction có thể gọi accessor thêm lần

Đây là rủi ro quan trọng khi *mục tiêu chính chỉ là loại cast*:

```java
record Counted(int value) {
    static int reads;
    public int value() {
        reads++;
        return value;
    }
}
```

So sánh:

```java
static boolean typeOnly(Object input) {
    return input instanceof Counted;
}

static boolean deconstruct(Object input) {
    return input instanceof Counted(var n);
}
```

Cả hai có thể trả `true` với cùng một `Counted`, nhưng **record pattern gọi accessor** để tách component, làm tăng biến đếm `reads`. Nếu accessor có side effect, ném exception hoặc tính toán tốn kém, thay type check bằng record pattern có thể làm thay đổi kết quả ngoài ý muốn.

**Tiêu chí DoD:** Chỉ áp dụng record deconstruction khi thực sự cần component và đã đánh giá tác dụng phụ của việc gọi accessor. Khi chỉ cần loại cast, `input instanceof Counted c` thường là cách chuyển đổi an toàn hơn.

### 4.6. Generic và dữ liệu mutable

Một cast như `(List<String>) input` không thể được chứng minh đúng hoàn toàn chỉ nhờ runtime type checking vì **type erasure**. `List<?>` kiểm tra kiểu container, không xác minh toàn bộ kiểu phần tử; không thay unchecked cast bằng unchecked cast khác mà không ghi rõ rủi ro.

Pattern matching cũng **không sao chép** đối tượng hoặc component. Nếu logic cũ truyền/trả cùng một `List` mutable hoặc mảng, mã mới vẫn có thể tiếp xúc cùng tham chiếu. Chỉ tạo defensive copy nếu đó là yêu cầu hợp đồng và test xác nhận tác động.

## 5. Thiết kế test làm tiêu chí chấp nhận

Test nên được phân lớp. Không có một số phần trăm coverage cố định nào tự chứng minh refactor đúng; ưu tiên các đường logic mang rủi ro.

### 5.1. Ma trận kiểm thử trước–sau

Với một phương thức phân loại `String`, `Integer`, `Point`, hãy chuẩn bị tối thiểu:

| Nhóm đầu vào | Ví dụ | Điều cần so |
| --- | --- | --- |
| Kiểu khớp bình thường | `"Java"`, `7`, `Point(2,3)` | Giá trị trả về, định dạng |
| Biên trong cùng kiểu | `""`, `"   "`, `-2`, `Point(-1,0)` | Điều kiện blank/âm/zero |
| Kiểu khác nhưng liên quan | `StringBuilder` nếu có `CharSequence` | Độ ưu tiên và fallback |
| Kiểu không liên quan | `new Object()` | Fallback, exception |
| Giá trị `null` | `null` | Fallback hay exception theo hợp đồng |
| Component `null` | Record có component reference bằng `null` | Nested pattern/guard và getter |
| Cast không guard | `(String) Integer.valueOf(42)` | `ClassCastException` có được bảo toàn? |
| Side effect | Record accessor có đếm số lần gọi | Không có đọc/thao tác phụ thêm |
| Generic container | `List<String>`, `List<Integer>` | Không giả định sai element type |
| Subclass/extension | Subtype hoặc sealed hierarchy hiện có | Không mất nhánh, không đổi precedence |

Test thường gồm ba loại bằng chứng:

1. **Regression tests** chạy lại những tình huống đã biết quan trọng.
2. **Differential tests** cho cùng input chạy mã cũ và mã refactor; so output và, khi hợp đồng yêu cầu, so loại exception và side effect.
3. **Negative/boundary tests** chủ động kiểm tra `null`, sai kiểu, kiểu con, boundary, component lỗi, guard đúng/sai.

Đối với hàm có tính ngẫu nhiên, thời gian, I/O hoặc dữ liệu đồng thời, cần kiểm soát nguồn không xác định trước khi so trực tiếp. Nếu test chỉ so `String` đầu ra, nó chưa chứng minh tương đương về exception, log, số lần gọi dependency hoặc race condition.

### 5.2. Mức phủ cần chứng minh

Đối với chuỗi phân loại, mỗi nhánh có ý nghĩa phải có ít nhất một test chứng minh nó được chọn. Mỗi guard cần trường hợp đúng và sai; `null` phải có kỳ vọng rõ. Khi module có quy định coverage, giữ ngưỡng hiện hành. Nếu chưa có, thiết lập ngưỡng theo độ rủi ro và những nhánh thực sự cần bảo vệ, thay vì khẳng định một con số tuỳ ý như "100% coverage là đủ".

**Exit criterion:** Nếu test phát hiện khác biệt, phải phân loại là bug refactor hay thay đổi được yêu cầu; không chỉnh expected output chỉ để test xanh khi chưa giải thích nguyên nhân.

## 6. Chương trình Java 21 hoàn chỉnh: tự so mã cũ và mã mới

Tạo tệp **`RefactorDoneDemo.java`** dưới đây. Chương trình có ba cách triển khai: mã legacy, refactor dùng type pattern, refactor dùng `switch` pattern. Nó kiểm tra **parity** cho nhiều input, sau đó cố ý cho thấy hai khác biệt hành vi mà test hồi quy phải bắt được.

```java
import java.util.function.IntSupplier;

public class RefactorDoneDemo {
    record Point(int x, int y) {}
    record Counted(int value) {
        static int reads;
        public int value() {
            reads++;
            return value;
        }
    }

    static String legacy(Object input) {
        if (input instanceof String) {
            String text = (String) input;
            return text.isBlank() ? "blank" : "text:" + text.trim();
        }
        if (input instanceof Integer) {
            Integer number = (Integer) input;
            return "int:" + number;
        }
        if (input instanceof Point) {
            Point point = (Point) input;
            return "point:" + point.x() + "," + point.y();
        }
        return "other";
    }

    static String refactored(Object input) {
        if (input instanceof String text) {
            return text.isBlank() ? "blank" : "text:" + text.trim();
        }
        if (input instanceof Integer number) {
            return "int:" + number;
        }
        if (input instanceof Point point) {
            return "point:" + point.x() + "," + point.y();
        }
        return "other";
    }

    static String asSwitch(Object input) {
        return switch (input) {
            case String text ->
                    text.isBlank() ? "blank" : "text:" + text.trim();
            case Integer number -> "int:" + number;
            case Point point -> "point:" + point.x() + "," + point.y();
            case null -> "other";
            default -> "other";
        };
    }

    static int strictCast(Object input) {
        return ((String) input).length();
    }

    static int changedSemantics(Object input) {
        return input instanceof String text ? text.length() : -1;
    }

    static String outcome(IntSupplier supplier) {
        try {
            return "returned " + supplier.getAsInt();
        } catch (RuntimeException error) {
            return error.getClass().getSimpleName();
        }
    }

    static boolean typeOnly(Object input) {
        return input instanceof Counted;
    }

    static boolean deconstruct(Object input) {
        return input instanceof Counted(var n);
    }

    public static void main(String[] args) {
        Object[] cases = {
                "  Java  ", "", "   ", 7, -2, new Point(2, 3),
                new Point(-1, 0), new StringBuilder("x"), null
        };
        for (Object input : cases) {
            String expected = legacy(input);
            String actual = refactored(input);
            String alternate = asSwitch(input);
            if (!expected.equals(actual) || !expected.equals(alternate)) {
                throw new AssertionError("Behavior mismatch for " + input);
            }
            System.out.println(expected);
        }
        System.out.println("PARITY PASS: " + cases.length);

        System.out.println("cast 42: " + outcome(() -> strictCast(42)));
        System.out.println("pattern 42: " + outcome(() -> changedSemantics(42)));
        System.out.println("cast null: " + outcome(() -> strictCast(null)));
        System.out.println("pattern null: " + outcome(() -> changedSemantics(null)));

        Counted counted = new Counted(4);
        System.out.println("type-only: " + typeOnly(counted)
                + ", reads=" + Counted.reads);
        System.out.println("deconstruct: " + deconstruct(counted)
                + ", reads=" + Counted.reads);
    }
}
```

Chạy với JDK 21 trở lên:

```bash
javac --release 21 RefactorDoneDemo.java
java RefactorDoneDemo
```

**stdout chính xác:**

```text
text:Java
blank
blank
int:7
int:-2
point:2,3
point:-1,0
other
other
PARITY PASS: 9
cast 42: ClassCastException
pattern 42: returned -1
cast null: NullPointerException
pattern null: returned -1
type-only: true, reads=0
deconstruct: true, reads=1
```

### 6.1. Đọc kết quả đúng cách

- Chín test trong vòng lặp so sánh `legacy`, `refactored` và `asSwitch`. Nếu có bất kỳ khác biệt nào, chương trình ném `AssertionError`; khi chạy đến dòng `PARITY PASS: 9`, tất cả chín ca đã qua.
- `String` blank và chứa khoảng trắng được kiểm tra riêng, tránh cho rằng test chuỗi thường đã đủ.
- `StringBuilder` là một subtype của `CharSequence` nhưng không phải `String`; nó đi vào fallback đúng như mã cũ.
- `null` được cho rơi vào `"other"` cả trong `if` legacy lẫn trong `switch` expression nhờ `case null`.
- Hai ca `strictCast` và `changedSemantics` **cố ý khác nhau**: cast trực tiếp ném exception với sai kiểu hoặc `null`, còn pattern version trả `-1`. Đây là tín hiệu **NOT DONE cho refactor không đổi hợp đồng**, trừ khi thay đổi đã được phê duyệt.
- `typeOnly` chỉ kiểm tra class; `deconstruct` truy cập accessor `Counted.value()`, làm `reads` tăng từ 0 lên 1. Nếu accessor có tác dụng phụ, cần đánh giá trước khi chọn record pattern.

### 6.2. Vì sao test này chưa phải chứng minh tuyệt đối?

Chín ca là mẫu minh hoạ, không bao phủ mọi input hoặc trạng thái hệ thống. Với API thật, cần test thêm subtype, generic types, phụ thuộc bên ngoài, ngoại lệ, concurrency và môi trường triển khai phù hợp. Chương trình chỉ chứng minh cụ thể **các đầu vào đã thử**, không thay thế code review hay hợp đồng của hệ thống.

Việc dùng `throw new AssertionError` trực tiếp (thay vì câu lệnh `assert`) giúp phép so chạy cả khi JVM không bật cờ `-ea`. Nếu dự án dùng JUnit/TestNG, nên chuyển ma trận parity thành test tự động được chạy trong CI.

## 7. Các lỗi biên dịch cần kiểm tra khi refactor

Không chỉ có lỗi logic lúc chạy. Pattern syntax có thêm các quy tắc an toàn lúc biên dịch.

### 7.1. Biến pattern ngoài phạm vi

```java
// CỐ Ý SAI — không biên dịch:
return input instanceof String text || text.isBlank();
```

Khi `instanceof` trả `false`, vế phải `||` mới được đánh giá nhưng `text` chưa được bind. Cách đúng nếu muốn chuỗi không blank:

```java
return input instanceof String text && !text.isBlank();
```

### 7.2. Nhánh type pattern bị dominated

```java
// CỐ Ý SAI — không biên dịch:
return switch (input) {
    case CharSequence chars -> "sequence";
    case String text -> "string";
    case null -> "null";
    default -> "other";
};
```

Mọi `String` đều là `CharSequence`, nên case đầu bao phủ case sau. Cần đặt `case String` trước `case CharSequence`.

### 7.3. Khác biệt giữa `var` và typed component trong record pattern

`Point(var x, var y)` bind cả hai giá trị `int`, không có rủi ro `null` ở các component nguyên thủy. Nhưng `record Person(String name) {}` có thể chứa `name == null`: `Person(var name)` match và bind `null`; `Person(String name)` không match component `null`. Khi refactor từ accessor sang nested pattern, cần kiểm tra ca component `null` để bảo đảm hành vi mong muốn.

### 7.4. Đừng dùng match pattern để khẳng định generic tham số hóa

`obj instanceof java.util.List<?> list` có thể kiểm tra rằng đối tượng là một `List`, nhưng không xác nhận mọi phần tử là `String`. Nếu code cũ có cast unchecked, refactor chuẩn chỉ khi thiết kế API/test xác minh dữ liệu và bảo đảm không tạo thêm cảnh báo unchecked.

**Điều kiện hoàn tất:** Không còn compiler errors, warning mới gây rủi ro hoặc sự thay đổi hành vi không được giải thích; bản build theo mức Java thực tế đã được CI xác minh.

## 8. Checklist kiểm tra sau khi viết mã

Có thể gắn trực tiếp checklist này vào PR, mỗi mục cần trạng thái và dẫn chứng:

- [ ] Xác định commit baseline, các phương thức được refactor và những hành vi nằm ngoài phạm vi.
- [ ] Liệt kê các cast được thay; các cast bắt buộc giữ lại đều có lý do.
- [ ] Biên dịch bằng target Java chính thức của dự án; không thêm preview flags nếu không cần.
- [ ] Bảo toàn kết quả cho input bình thường và các kiểu/subtype có trong hợp đồng.
- [ ] Có test riêng cho `null`, blank/empty, boundary và wrong type.
- [ ] So sánh exception quan trọng với bản cũ; thay đổi exception phải được phê duyệt.
- [ ] Kiểm tra thứ tự nhánh `if/else` và dominance/exhaustiveness khi đổi sang `switch`.
- [ ] Kiểm tra `&&`, `||`, phủ định, phạm vi pattern variables và `when` guards.
- [ ] Đánh giá số lần gọi accessor, side effects, mutation và các phụ thuộc đồng thời nếu có.
- [ ] Không thêm raw/unchecked casts hoặc giả định sai generic element types.
- [ ] Các test liên quan đã chạy, CI và static analysis theo chính sách dự án đạt.
- [ ] Diff dễ review, không trộn một thay đổi nghiệp vụ chưa phê duyệt vào refactor.
- [ ] Các trường hợp không tương đương đã được xử lý hoặc ghi rõ là thay đổi có chủ ý.
- [ ] Có kế hoạch theo dõi sau merge/deploy và cách hoàn tác nếu tác động lớn.

Checklist không phải thủ tục hình thức. Nếu một mục không áp dụng (ví dụ không có dữ liệu mutable hoặc không thay `switch`), đánh dấu **N/A kèm lý do** thay vì tuyên bố đã test điều không tồn tại.

## 9. Tự động hóa tiêu chí bằng build, test và CI

Một quy trình đơn giản:

1. **Compile gate:** Build trên JDK đích, tối thiểu `javac --release 21` cho chương trình dùng Java 21. Trong dự án thực tế, dùng cấu hình Maven/Gradle mà repository đã thiết lập.
2. **Regression gate:** Chạy test suite hiện hành và các test mới cho các nhánh đã thay.
3. **Diff gate:** Chạy cùng bộ input trên baseline và phiên bản refactor; so đầu ra và hợp đồng exception. Nếu có side effect, bổ sung spy/fake/counter.
4. **Static gate:** Chạy các công cụ kiểm tra tĩnh/lint theo chính sách dự án, tập trung unchecked casts, unreachable/dominated cases và yêu cầu API.
5. **Review gate:** Reviewer thấy được bảng thay đổi, edge cases đã test và lý do dùng type pattern/record pattern/`switch`.
6. **Release gate:** Nếu thay đổi chạm hành vi production rủi ro cao, ghi cách quan sát lỗi, metric, kế hoạch rollback.

Với tệp ví dụ trong mục 6, hai lệnh này là đủ để kiểm tra bằng JDK:

```bash
javac --release 21 RefactorDoneDemo.java
java RefactorDoneDemo
```

Với repository dùng Maven Wrapper hoặc Gradle Wrapper, chỉ dùng lệnh thực tế tồn tại và phù hợp môi trường, ví dụ `./mvnw test` hoặc `./gradlew test` trên hệ hỗ trợ shell tương ứng; các lệnh này **không phải mặc định đã có** ở mọi dự án.

### Tiêu chí cho CI pass

Một PR chỉ đủ bằng chứng khi pipeline thực sự chạy trên commit được review, chứ không phải test "đã từng xanh" trên máy cục bộ với phiên bản mã khác. Nếu CI có điều kiện chạy test, bảo đảm phần mã được thay đã được test bởi job phù hợp. Không tự ý tắt job đang đỏ hoặc giảm ngưỡng quality gate để biến refactor thành hoàn tất.

Với hệ thống nhiều phiên bản Java, cần phân biệt: dùng JDK mới để biên dịch với `--release 21` là khác với việc chạy integration tests trên runtime thực sự của hệ thống. Nếu deploy dùng Java 21, nên xác nhận ít nhất một môi trường chạy đúng Java 21 ở quy trình kiểm thử phù hợp.

## 10. Tiêu chí review, rollout và rollback

### Review thay đổi

PR description nên ghi ngắn, rõ:

- **Trước/Sau:** một ví dụ đại diện, không cần dán toàn bộ diff.
- **Hợp đồng giữ nguyên:** đầu ra, `null`, ngoại lệ, thứ tự nhánh, side effects.
- **Các chỗ đổi có chủ ý:** chỉ rõ lý do và test thay vì gắn nhãn "refactor".
- **Test evidence:** các lệnh/job đã chạy và nhóm input đã kiểm tra.
- **Rủi ro còn lại:** phần chưa bao phủ và cách hạn chế tác động.

Reviewer nên ưu tiên kiểm tra các thay đổi có thể ẩn trong mã ngắn hơn: một cast direct bị thay thành fallback, một `switch` không có `case null`, thứ tự điều kiện khác, hoặc record pattern gọi accessor thêm lần.

### Rollout và khả năng quay lại

Với refactor nhỏ, không thay đổi hợp đồng và test đầy đủ, triển khai có thể theo quy trình thông thường. Với refactor lan qua nhiều module, runtime hoặc API, nên cân nhắc chia PR theo nhóm chức năng, quan sát các chỉ số lỗi hiện có sau deploy, có commit/release dễ revert và giữ đường xử lý an toàn khi cần.

**Rollback không có nghĩa là giữ mã legacy mãi mãi.** Đây là cách bảo vệ người dùng nếu phát hiện sai lệch chưa được test; sau khi phân tích nguyên nhân và bổ sung test, có thể áp dụng lại refactor đã sửa.

## 11. Khi nào phải đánh dấu NOT DONE?

Một thay đổi chưa đạt DoD nếu gặp ít nhất một trong các tình huống sau mà chưa có xử lý hoặc phê duyệt:

| Tình huống | Vì sao chưa hoàn tất? |
| --- | --- |
| Mới compile local, chưa test behavior | Thiếu bằng chứng tương đương về đầu ra/nhánh |
| Đổi cast direct từ throw exception thành fallback | Thay hợp đồng hành vi, chưa được xác nhận |
| Đổi `if/else` thành `switch` làm `null` ném NPE | Mất nhánh xử lý trước đây |
| Dùng record deconstruction gây gọi accessor thêm lần | Side effect hoặc exception có thể khác |
| Đảo thứ tự pattern kiểu cha/con | Compiler báo dominance hoặc thay precedence |
| Đặt test với `assert` nhưng chạy không có `-ea` | Điều kiện test có thể không được thực thi |
| Chỉ test một chuỗi hợp lệ | Không phủ blank, null, wrong type, subtype |
| Có warning unchecked mới, đã bỏ qua không lý do | Rủi ro type safety chưa giải quyết |
| Test expectation thay theo output mới để "xanh" | Mất baseline mà không đánh giá thay đổi nghiệp vụ |
| CI xanh trên commit cũ, commit mới chưa chạy | Chưa xác minh đúng phiên bản được merge |
| Còn thay đổi mở rộng ngoài phạm vi chưa review | Không thể kết luận đây là refactor thuần túy |

**Quyết định hoàn tất:** Chỉ xác nhận **DONE** khi phạm vi rõ, các hành vi được bảo toàn hoặc thay đổi được duyệt, kiểm thử đủ theo rủi ro, build và CI bắt buộc đạt, review đã xong và rủi ro triển khai có biện pháp kiểm soát.

## 12. Câu hỏi tự kiểm tra

**1.** Tại sao "không còn cast trong diff" không đủ làm DoD?  
*Trả lời:* Vì mã mới vẫn có thể đổi `null`, exception, độ ưu tiên nhánh hoặc side effect.

**2.** Refactor `(String) input` trực tiếp thành `input instanceof String s ? ... : fallback` có luôn giữ semantics không?  
*Trả lời:* Không. Cast trực tiếp có thể ném `ClassCastException` với sai kiểu, còn pattern có thể đi vào fallback.

**3.** Vì sao thay chuỗi `if/else` bằng `switch` cần test `null`?  
*Trả lời:* `instanceof` với `null` là `false`, nhưng pattern `switch` không tự đưa `null` vào `default`; cần `case null` nếu muốn giữ fallback.

**4.** Trong refactor legacy casts, khi nào chọn type pattern thay record pattern?  
*Trả lời:* Khi chỉ cần xác định kiểu và loại bỏ cast. Record pattern hữu ích khi thực sự cần component và đã xét accessor/side effect.

**5.** Thử chín đầu vào và được `PARITY PASS: 9` đã chứng minh tương đương tuyệt đối chưa?  
*Trả lời:* Chưa. Nó chỉ chứng minh kết quả của chín trường hợp đã thử; còn exception, trạng thái, input khác và phụ thuộc runtime.

**6.** Nếu phát hiện output khác vì sửa bug cũ, có phải bỏ thay đổi đó không?  
*Trả lời:* Không nhất thiết; nhưng phải tách/ghi rõ thay đổi hành vi, có expected behavior và sự phê duyệt phù hợp.

**7.** Tại sao nên có regression test cho `ClassCastException` và `NullPointerException`?  
*Trả lời:* Caller có thể phụ thuộc vào hành vi exception; pattern matching không tự bảo đảm cùng loại/điều kiện ngoại lệ như cast cũ.

**8.** Vì sao test coverage cao vẫn có thể chưa đủ?  
*Trả lời:* Coverage không chứng minh đầy đủ expected behavior, nhất là input biên, thứ tự side effect, tương thích API và dữ liệu ngoài dự kiến.

**9.** Nếu `case CharSequence` đứng trước `case String` trong Java 21, DoD bị ảnh hưởng thế nào?  
*Trả lời:* Compiler báo dominance; compile gate không đạt.

## Tham khảo

- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [Oracle Java SE 21 — Pattern Matching for instanceof](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-instanceof.html)
- [Oracle Java SE 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
- [JLS SE 21 §15.20.2 — The instanceof Operator](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.20.2)
- [JLS SE 21 §14.11 — The switch Statement](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11)
