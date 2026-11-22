# Exception trong accessor của record pattern (Java 21)

## 1. Vấn đề cốt lõi: record pattern không chỉ “nhìn” vào các trường

Một **record pattern** phân rã một đối tượng record để kiểm tra và ràng buộc các thành phần của nó:

```java
record Label(String value) {}

Object candidate = new Label("OK");
if (candidate instanceof Label(var labelText)) {
    System.out.println(labelText);
}
```

Kết quả là `OK`. Điều dễ bỏ sót: Java **lấy giá trị thành phần bằng cách gọi accessor tương ứng**, chẳng hạn `Label.value()`. Trong trường hợp accessor do compiler sinh, nó đơn giản trả về trường thành phần. Nhưng một record **được phép tự khai báo accessor** với thân phương thức riêng, và thân ấy có thể ném ngoại lệ không được kiểm tra (*unchecked exception*).

Vì vậy, với:

```java
if (candidate instanceof Label(var labelText)) {
    // ...
}
```

việc phân rã có thể làm thêm công việc, thậm chí thất bại **trước khi đi vào nhánh `if`**. Không được mặc định rằng record pattern chỉ là phép kiểm tra kiểu thuần túy, không có lời gọi phương thức.

Đây là trọng tâm của bài: **nếu accessor được gọi trong quá trình khớp record pattern ném ngoại lệ thì pattern matching kết thúc bất thường bằng `java.lang.MatchException`; ngoại lệ gốc nằm trong `getCause()`**. Đây là hành vi được mô tả trong Java Language Specification 21, `14.30.2. Nó khác với việc mẫu không khớp và cũng khác với gọi accessor trực tiếp.

## 2. Accessor của record là gì?

Với:

```java
record Ticket(String code, int priority) {}
```

Java có các accessor `code()` và `priority()`. Nếu không tự khai báo, chúng trả về trường thành phần tương ứng:

```java
Ticket ticket = new Ticket("TK-1", 3);
System.out.println(ticket.code());     // TK-1
System.out.println(ticket.priority()); // 3
```

Một record cũng có thể khai báo accessor tường minh:

```java
record Label(String value) {
    public String value() {
        if (value == null) {
            throw new IllegalStateException("missing label");
        }
        return value.strip();
    }
}
```

Trường `value` vẫn là trường thành phần của record, còn accessor `value()` giờ có **logic tùy chỉnh**:

- Trả về phiên bản loại bỏ khoảng trắng ở hai đầu bằng `strip()` khi có dữ liệu.
- Ném `IllegalStateException` nếu giá trị thành phần là `null`.

Đây là ví dụ **cố ý tạo accessor có nguy cơ lỗi** để quan sát hành vi của pattern matching, không phải thiết kế nên ưu tiên cho record dữ liệu bình thường. Nếu một component bắt buộc khác `null` hoặc cần chuẩn hóa, thường nên kiểm tra/chuẩn hóa **ngay trong constructor** để không tạo ra record có trạng thái bất hợp lệ.

**Giới hạn ngôn ngữ:** một accessor của record phải là phương thức instance `public`, không có tham số, có kiểu trả về giống component và **không được có mệnh đề `throws`**. Nó vẫn có thể ném ngoại lệ unchecked như `IllegalStateException`, `IllegalArgumentException`, `NullPointerException` hoặc `Error` theo quy tắc Java; việc không khai báo `throws` không bảo đảm rằng accessor không thể thất bại.

Ví dụ sau **cố ý không biên dịch**:

```java
record BadAccessor(String code) {
    public String code() throws java.io.IOException {
        return code;
    }
}
```

Compiler sẽ báo dạng `throws clause not allowed for accessor method`. Nếu accessor cần gọi API có checked exception, không thể chỉ thêm `throws IOException`; hãy thiết kế lại nơi lấy dữ liệu/kiểm tra, hoặc xử lý ngoại lệ ở bên trong theo hợp đồng phù hợp.

## 3. Ngoại lệ trong accessor được xử lý thế nào khi matching?

Với một giá trị record `r` và mẫu `R(...)`, quá trình record matching cần nhận từng giá trị component thông qua accessor của `r`. Khi một accessor bị gọi và ném ngoại lệ `cause`:

```text
candidate (đã là instance của R)
        │
        ▼
thử khớp R(componentPattern...)
        │
        ▼
gọi accessor của record để lấy component
        │
        ├── trả về dữ liệu ──► tiếp tục khớp mẫu con
        │
        └── ném exception E
                  │
                  ▼
          MatchException
          getCause() == E
                  │
                  ▼
   thoát khỏi việc matching, không chạy case/if body
```

**Không phải “mẫu không khớp”**. Một mẫu không khớp bình thường có thể khiến `instanceof` trả `false` hoặc `switch` thử case khác. Nhưng accessor ném ngoại lệ khiến phép so khớp **kết thúc bất thường**, nên:

- `if (obj instanceof R(...))` không đi tiếp tới nhánh `else` như một trường hợp `false` thông thường.
- `switch` không tự chuyển sang `default` hoặc `case` kế tiếp để “bỏ qua” record lỗi.
- Đoạn thân `if` hoặc thân `case` chưa được thực thi, nên `try/catch` **đặt bên trong** thân đó không thể bắt ngoại lệ đã xảy ra trong khi đánh giá mẫu.
- Để xử lý, phải đặt `try/catch` **bao quanh toàn bộ phép khớp** (`instanceof` hoặc `switch`) hay xử lý dữ liệu trước khi matching.

Java 21 sử dụng `java.lang.MatchException` để biểu diễn lỗi bất ngờ của pattern matching; với lỗi bắt nguồn từ accessor, ngoại lệ gốc được gắn làm **cause**. Nó không thay thế mọi kiểu ngoại lệ có thể xảy ra ở các phần khác của chương trình.

## 4. Ví dụ tối thiểu: cùng đối tượng, ba kết quả khác nhau

Giả sử record `Label` có accessor ở mục 2:

```java
Label bad = new Label(null);
Object candidate = bad;
```

### 4.1. Gọi accessor trực tiếp

```java
bad.value();
```

Lời gọi trực tiếp chạy thân `value()` và ném **`IllegalStateException`** với message `missing label`. Không có record pattern nên không có quy tắc tự chuyển sang `MatchException`.

### 4.2. Chỉ kiểm tra kiểu bằng type pattern

```java
if (candidate instanceof Label label) {
    System.out.println("matched type");
}
```

Mẫu `Label label` chỉ kiểm tra kiểu của đối tượng và ràng buộc tham chiếu `label`; nó **không cần gọi `label.value()`**. Vì thế, dù component bên trong là `null`, nhánh này vẫn chạy và in `matched type`. Nếu thân nhánh sau đó chủ động gọi `label.value()`, lỗi từ lời gọi **trực tiếp** vẫn là `IllegalStateException`.

### 4.3. Phân rã bằng record pattern

```java
try {
    if (candidate instanceof Label(var labelText)) {
        System.out.println(labelText);
    }
} catch (MatchException ex) {
    System.out.println(ex.getCause().getClass().getSimpleName());
}
```

Kết quả:

```text
IllegalStateException
```

Khi khớp `Label(var labelText)`, Java cần gọi `value()`. Accessor ném `IllegalStateException`; pattern matching ném `MatchException` và cause là ngoại lệ gốc. Thân `if` không chạy.

Đây là lý do không được đồng nhất `candidate instanceof Label label` với `candidate instanceof Label(var labelText)` về **tác động thực thi**. Hai mẫu liên quan cùng một record nhưng mẫu thứ hai truy xuất component qua accessor.

## 5. Ví dụ đầy đủ Java 21: lỗi lồng nhau, null và guard

Lưu chương trình sau thành **`RecordAccessorExceptionDemo.java`**. Chương trình minh họa:

1. Record pattern lấy giá trị qua accessor tùy chỉnh.
2. Type pattern không cần truy xuất component.
3. Record pattern lồng nhau có thể phát sinh `MatchException`.
4. `var` trong pattern có thể nhận component `null` khi accessor trả về bình thường.
5. Ngoại lệ trong `when` khác ngoại lệ do accessor.
6. Gọi accessor trực tiếp không tự bị bọc.

```java
import java.util.function.Supplier;

public class RecordAccessorExceptionDemo {
    record Label(String value) {
        public String value() {
            if (value == null) {
                throw new IllegalStateException("missing label");
            }
            return value.strip();
        }
    }

    record Parcel(String parcelId, Label label) {}
    record Plain(String value) {}

    static String recordPattern(Object candidate) {
        if (candidate instanceof Label(var labelText)) {
            return "label:" + labelText;
        }
        return "not Label";
    }

    static String typePattern(Object candidate) {
        if (candidate instanceof Label label) {
            return "type:" + label.getClass().getSimpleName();
        }
        return "not Label";
    }

    static String nestedPattern(Object candidate) {
        if (candidate instanceof Parcel(
                var parcelId, Label(var labelText))) {
            return parcelId + ":" + labelText;
        }
        return "no nested match";
    }

    static String shallowPattern(Object candidate) {
        if (candidate instanceof Parcel(var parcelId, var label)) {
            return parcelId + ":label="
                    + (label == null ? "null" : "present");
        }
        return "not Parcel";
    }

    static String switchRecord(Object candidate) {
        return switch (candidate) {
            case null -> "selector:null";
            case Label(var labelText) -> "switch:" + labelText;
            default -> "other";
        };
    }

    static boolean rejectFromGuard(String labelText) {
        throw new IllegalArgumentException("guard rejected");
    }

    static String guardThrows(Object candidate) {
        return switch (candidate) {
            case Label(var labelText)
                    when rejectFromGuard(labelText) -> "blocked";
            case Label(var labelText) -> "allowed:" + labelText;
            default -> "other";
        };
    }

    static String plainPattern(Object candidate) {
        if (candidate instanceof Plain(var text)) {
            return text == null ? "plain:null" : "plain:" + text;
        }
        return "not Plain";
    }

    static void probe(String name, Supplier<String> operation) {
        try {
            System.out.println(name + "=" + operation.get());
        } catch (MatchException ex) {
            Throwable cause = ex.getCause();
            System.out.println(name + "=MatchException cause="
                    + cause.getClass().getSimpleName()
                    + ":" + cause.getMessage());
        } catch (IllegalArgumentException ex) {
            System.out.println(name + "=IllegalArgumentException:"
                    + ex.getMessage());
        }
    }

    public static void main(String[] args) {
        Label good = new Label("  OK  ");
        Label bad = new Label(null);
        Parcel badParcel = new Parcel("P-7", bad);
        Parcel nullParcel = new Parcel("P-8", null);

        probe("record-good", () -> recordPattern(good));
        probe("type-bad", () -> typePattern(bad));
        probe("record-bad", () -> recordPattern(bad));
        probe("nested-bad", () -> nestedPattern(badParcel));
        probe("shallow-bad", () -> shallowPattern(badParcel));
        probe("nested-null", () -> nestedPattern(nullParcel));
        probe("shallow-null", () -> shallowPattern(nullParcel));
        probe("switch-bad", () -> switchRecord(bad));
        probe("switch-null", () -> switchRecord(null));
        probe("plain-null", () -> plainPattern(new Plain(null)));
        probe("guard-ex", () -> guardThrows(good));

        try {
            bad.value();
        } catch (IllegalStateException ex) {
            System.out.println("direct=IllegalStateException:"
                    + ex.getMessage());
        }
    }
}
```

Biên dịch và chạy với JDK 21 trở lên:

```bash
javac --release 21 -encoding UTF-8 RecordAccessorExceptionDemo.java
java RecordAccessorExceptionDemo
```

**Đầu ra chính xác:**

```text
record-good=label:OK
type-bad=type:Label
record-bad=MatchException cause=IllegalStateException:missing label
nested-bad=MatchException cause=IllegalStateException:missing label
shallow-bad=P-7:label=present
nested-null=no nested match
shallow-null=P-8:label=null
switch-bad=MatchException cause=IllegalStateException:missing label
switch-null=selector:null
plain-null=plain:null
guard-ex=IllegalArgumentException:guard rejected
direct=IllegalStateException:missing label
```

Đây là các giá trị được kiểm chứng khi chạy chương trình Java 21. Chúng minh họa hành vi ngôn ngữ; thứ tự các lời gọi được in trong `main` là thứ tự các lệnh `probe(...)` được viết, không phải một cam kết về thứ tự nội bộ của các accessor trong mọi record pattern phức tạp.

## 6. Phân tích các trường hợp trong chương trình

### 6.1. Record pattern có thể nhận dữ liệu đã qua xử lý của accessor

`record-good=label:OK`: đối tượng `Label("  OK  ")` được phân rã và gọi accessor `value()`; kết quả là chuỗi đã `strip()`. Pattern variable `labelText` nhận giá trị do accessor **trả về**, không có phép truy cập “tắt” vào trường private của record.

Đây cũng là dấu hiệu thiết kế cần cân nhắc: accessor trả kết quả khác giá trị lưu trong component có thể gây ngạc nhiên cho người dùng record và ảnh hưởng các giả định về tính chất dữ liệu của record. Nếu cần chuẩn hóa chuỗi, nên cân nhắc làm tại thời điểm xây dựng record để accessor giữ vai trò truy xuất ổn định.

### 6.2. Type pattern không giống record pattern

`type-bad=type:Label`: `bad` có kiểu `Label` nên type pattern khớp. Việc lấy `label.getClass().getSimpleName()` không cần gọi `value()`, vì thế không phát sinh lỗi.

`record-bad=MatchException cause=IllegalStateException:missing label`: record pattern phải gọi `value()` và gặp lỗi. `if` không trả `false` rồi đi vào `return "not Label"`; hàm `recordPattern` bị ngắt bởi exception.

### 6.3. Accessor lỗi ở tầng con của mẫu lồng nhau

`nested-bad` nhận `Parcel("P-7", Label(null))`. Mẫu:

```java
Parcel(var parcelId, Label(var labelText))
```

trước tiên phải lấy giá trị `Parcel.label()` để xét mẫu `Label(...)`. Khi đối tượng con `Label` tồn tại nhưng `Label.value()` ném lỗi, cả quá trình matching lồng nhau kết thúc bằng `MatchException`.

Trong khi đó, `shallow-bad=P-7:label=present` vì:

```java
Parcel(var parcelId, var label)
```

chỉ lấy các thành phần của `Parcel`. Mẫu này ràng buộc `label` là tham chiếu `Label` mà **không cần gọi `Label.value()`**. Nhưng nếu `Parcel.label()` được tự viết để ném ngoại lệ, bản thân mẫu nông đó cũng có thể bị `MatchException`. Chỉ dùng mẫu nông không tạo bảo đảm tổng quát rằng mọi accessor đều an toàn.

### 6.4. Component null không nhất thiết là exception

`nested-null=no nested match`: `Parcel("P-8", null)` có component `label` bằng `null`. Mẫu record con `Label(...)` **không khớp `null`**, nên `instanceof` hoàn tất bình thường với `false`; không có accessor của `Label` để gọi.

`shallow-null=P-8:label=null`: với `var label` là mẫu thành phần record, `null` có thể được ràng buộc vào biến tham chiếu. Mẫu nông vẫn khớp và xử lý `label == null` như một giá trị bình thường.

`plain-null=plain:null`: `Plain` chỉ có accessor do compiler sinh, trả `null`; mẫu `Plain(var text)` vẫn khớp và biến `text` nhận `null`. Đây không phải lỗi chỉ vì component mang `null`.

### 6.5. Switch không nuốt exception từ accessor

`switch-bad` cho thấy `case Label(var labelText)` cũng gây `MatchException` khi accessor lỗi. `default -> "other"` **không** được dùng như catch. Ngược lại, `switch-null=selector:null` chạy `case null` vì **selector** là `null`; lúc ấy không có record accessor nào được gọi.

### 6.6. Exception từ `when` khác exception từ accessor

`guard-ex=IllegalArgumentException:guard rejected` xuất hiện khi `guardThrows(good)`:

1. Mẫu `Label(var labelText)` khớp; accessor trả chuỗi bình thường.
2. Điều kiện `when rejectFromGuard(labelText)` được đánh giá.
3. Chính `rejectFromGuard` ném `IllegalArgumentException`.

Đây là lỗi **trong guard**, không phải lỗi do lời gọi accessor của record pattern, nên ngoại lệ đi ra trực tiếp theo quy tắc đánh giá biểu thức; không tự biến thành `MatchException`. Nhánh `case Label(...)` tiếp theo cũng không có cơ hội “chữa” lỗi bằng fallback vì đánh giá guard đã kết thúc bất thường.

### 6.7. Gọi accessor trực tiếp không bị bọc

`direct=IllegalStateException:missing label`: `bad.value()` được gọi trực tiếp, nên `IllegalStateException` được ném ra như đã viết trong accessor. `MatchException` chỉ xuất hiện vì quá trình **pattern matching** gặp lỗi trong khi ngầm gọi accessor.

## 7. So sánh chính xác các trường hợp dễ nhầm

| Tình huống | Điều xảy ra | Kết quả/cách xử lý |
| --- | --- | --- |
| `obj instanceof Label label`, component value lỗi nhưng không gọi accessor | Kiểm tra kiểu và ràng buộc tham chiếu | Khớp bình thường nếu đối tượng đúng kiểu và khác `null` |
| `obj instanceof Label(var text)`, accessor trả giá trị hợp lệ | Accessor được gọi để lấy component | Khớp, `text` là giá trị accessor trả về |
| `obj instanceof Label(var text)`, accessor ném unchecked exception | Matching bị ngắt bất thường | `MatchException`, `getCause()` là ngoại lệ gốc |
| `Parcel(var id, Label(var text))`, `label == null` | Record con không khớp | `instanceof` là `false`, không phải `MatchException` |
| `Parcel(var id, var label)`, `label == null` | Mẫu `var` nhận thành phần tham chiếu `null` | Có thể khớp bình thường |
| `Plain(var text)`, `text == null` | Accessor mặc định trả `null` | Có thể khớp bình thường |
| `switch (obj)` có `case R(...)` và accessor lỗi | Matching case bị ngắt | `MatchException`, không chuyển sang `default` |
| `switch (null)` có `case null` | Selector là `null` | Chạy `case null`, không gọi accessor |
| `switch (null)` không có `case null` phù hợp | Selector null | Thường ném `NullPointerException`, không phải lỗi accessor |
| `when condition(...)` ném lỗi | Lỗi khi đánh giá guard | Ngoại lệ từ guard lan truyền trực tiếp |
| `recordAccessor()` gọi trực tiếp | Lỗi trong lời gọi phương thức bình thường | Ném ngoại lệ gốc, không tự bọc `MatchException` |
| `getCandidate()` ném trước khi vào pattern | Lỗi tại biểu thức đầu vào | Ném ngoại lệ của `getCandidate()`, không phải lỗi accessor do pattern |

Bảng này tách bạch **khớp/không khớp** với **kết thúc bất thường**, và tách **điểm phát sinh exception** khỏi chỉ việc “có pattern ở gần đó”.

## 8. Đặt `try/catch` đúng vị trí

### Sai ý tưởng: đặt catch ở trong nhánh mà chưa chắc vào được

Không thể dựa vào phần thân `case` để xử lý lỗi của accessor dùng **trước** khi Java xác định case nào khớp:

```java
// Minh họa cách đặt catch không giải quyết lỗi matching.
switch (candidate) {
    case Label(var labelText) -> {
        try {
            System.out.println(labelText);
        } catch (MatchException ex) {
            System.out.println("accessor failed");
        }
    }
    default -> System.out.println("other");
}
```

Lỗi trong `Label.value()` xuất hiện **trước khi vào case body**, nên `catch` bên trong case không bắt được nó.

### Đúng vị trí: bao quanh toàn bộ việc matching

```java
try {
    switch (candidate) {
        case Label(var labelText) ->
                System.out.println("label:" + labelText);
        default ->
                System.out.println("other");
    }
} catch (MatchException ex) {
    Throwable cause = ex.getCause();
    System.out.println("record-pattern failed: " + cause);
}
```

Hai đoạn ở trên là **minh họa**, giả định đã khai báo `candidate` và `Label`; đoạn thứ hai đủ để mô tả vị trí `try/catch` hợp lệ.

Tương tự với `instanceof`:

```java
try {
    if (candidate instanceof Label(var labelText)) {
        System.out.println(labelText);
    }
} catch (MatchException ex) {
    // Xử lý lỗi khớp record pattern; có thể ghi nhận cause.
}
```

**Không nên bắt rồi bỏ qua mọi `MatchException`**. Nó cho biết quá trình pattern matching gặp lỗi bất thường, khác với trường hợp người dùng đưa kiểu khác. Khi phục hồi, phải dựa vào hợp đồng nghiệp vụ, bảo toàn nguyên nhân lỗi và không để hệ thống hiểu lầm rằng dữ liệu đã được xử lý thành công.

## 9. Thiết kế record để lỗi không phát sinh bất ngờ ở lúc matching

Cách tốt nhất không phải đặt `catch (MatchException)` khắp nơi, mà là **tránh accessor có logic bất ổn**.

### 9.1. Kiểm tra trong compact constructor

```java
import java.util.Objects;

record SafeLabel(String value) {
    SafeLabel {
        value = Objects.requireNonNull(value, "value").strip();
        if (value.isBlank()) {
            throw new IllegalArgumentException("blank label");
        }
    }
}
```

Đây là đoạn Java minh họa riêng (cần đặt trong một file/lớp hợp lệ khi biên dịch). Khi tạo `new SafeLabel(null)`, lỗi xảy ra **ngay trong constructor**, trước lúc có đối tượng hợp lệ để đem so khớp; nó **không** tự trở thành `MatchException` vì chưa có pattern matching. Sau khi xây dựng thành công, accessor `value()` do compiler sinh chỉ trả trường đã được chuẩn hóa.

**Lưu ý:** constructor có thể ném ngoại lệ bình thường; kiểu exception, thời điểm lỗi và hợp đồng API sẽ khác với kiểu lỗi phát sinh trong accessor khi matching. Không thay đổi thiết kế này trên hệ thống đang chạy mà bỏ qua kiểm thử tương thích hành vi.

### 9.2. Để accessor đơn giản và ổn định

Ưu tiên các accessor chỉ trả component đã có, không thực hiện I/O, truy vấn mạng/CSDL, xử lý lazy state khó đoán hoặc ném lỗi phụ thuộc điều kiện môi trường. Record được dùng với pattern matching như mô hình dữ liệu; các accessor có side effect dễ khiến thao tác tưởng là “chỉ kiểm tra kiểu” lại gây thay đổi trạng thái.

Không nên phụ thuộc vào số lần hay thứ tự gọi accessor trong quá trình matching phức tạp như một hợp đồng ứng dụng. Chỉ quan sát vài lượt chạy cụ thể **không chứng minh** compiler/JVM sẽ luôn gọi đúng một lần theo thứ tự mà code nghiệp vụ muốn. Nếu cần một lần truy xuất với thứ tự kiểm soát được, viết code lấy dữ liệu chủ động rồi xử lý.

### 9.3. Nếu phải truy xuất có thể lỗi, đặt thao tác có tên riêng

Thay vì nhét logic lấy dữ liệu từ service vào accessor:

```java
// Minh họa thiết kế: phương thức domain có tên phản ánh khả năng lỗi.
record CustomerRef(String id) {}

static String loadCustomerName(CustomerRef ref) {
    // Đây là nơi ứng dụng triển khai việc truy xuất/có thể thất bại.
    return ref.id();
}
```

Đây không phải một bản cài đặt service thật; nó cho thấy ý tưởng tách một thao tác có thể lỗi khỏi record accessor. Phần xử lý gọi `loadCustomerName(...)` một cách tường minh và quyết định bắt exception ở đúng tầng trách nhiệm.

### 9.4. Dùng type pattern nếu chưa cần phân rã

Nếu chỉ cần biết đầu vào là `Label` để quyết định bước tiếp theo, `instanceof Label label` có thể dễ hiểu và không bắt buộc gọi accessor `value()` ngay lúc đó. Tuy nhiên, nếu phần xử lý sau đó cần dữ liệu, lúc gọi accessor trực tiếp vẫn có thể lỗi. **Type pattern không “làm sạch” một record có accessor bất thường.**

## 10. Kiểm thử hồi quy và khả năng quan sát

Khi một record có accessor tùy chỉnh hoặc có dữ liệu không đáng tin, test nên phân biệt:

1. **Record hợp lệ:** accessor trả đúng giá trị; record pattern ràng buộc đúng component.
2. **Accessor ném lỗi:** assert `MatchException` và **`getCause()` đúng kiểu/message nguyên nhân**.
3. **Cùng object dưới type pattern:** khi chỉ kiểm tra kiểu, không có truy xuất component; xác nhận không xảy ra exception từ accessor.
4. **Nested record:** record ngoài không `null`, record con có accessor lỗi; xác nhận lỗi từ tầng con vẫn bọc bằng `MatchException`.
5. **Record con bằng `null`:** kiểm tra mẫu record lồng nhau không khớp bình thường; mẫu `var` có thể ràng buộc `null`.
6. **Selector `null`:** với `switch`, chính sách `case null` hoặc NPE phải rõ; không gộp lỗi null selector với lỗi accessor.
7. **Guard/nhánh xử lý ném lỗi:** kiểm tra nó lan truyền theo nguồn thực, không giả định mọi exception trong switch đều là `MatchException`.
8. **Side effects:** nếu có accessor tùy chỉnh, test cả trạng thái, log và số lần truy xuất, nhưng tốt hơn là refactor loại side effect khỏi accessor để tránh phụ thuộc đặc tính triển khai.
9. **Hợp đồng constructor:** test đầu vào `null`/rỗng/bất hợp lệ ngay khi tạo record thay vì chỉ phát hiện ở lúc khớp pattern.
10. **Java version:** chạy bằng JDK 21+ vì `RecordPattern(...)` và `MatchException` trong ngữ cảnh này là tính năng Java 21.

Ví dụ JUnit 5 (đoạn minh họa, cần JUnit trên classpath và record `Label` tương ứng):

```java
// import static org.junit.jupiter.api.Assertions.*;
// @org.junit.jupiter.api.Test
void accessorFailureIsWrapped() {
    Object candidate = new Label(null);

    MatchException ex = assertThrows(MatchException.class, () -> {
        boolean matched = candidate instanceof Label(var text);
        System.out.println(matched);
    });

    assertInstanceOf(IllegalStateException.class, ex.getCause());
    assertEquals("missing label", ex.getCause().getMessage());
}
```

Nếu đưa vào class test thật, mở comment cho các import/annotation và bảo đảm đã có `Label` trong phạm vi. Đây **không phải chương trình độc lập** như `RecordAccessorExceptionDemo.java` ở mục 5.

## 11. Các hiểu lầm thường gặp

### “`instanceof` thì chỉ true hoặc false, không thể ném lỗi”

Với **type pattern** thuần túy, kiểm tra kiểu thường chỉ trả kết quả phù hợp/không phù hợp. Nhưng **record pattern** phải lấy component bằng accessor; accessor có thể ném exception, khiến phép matching ném `MatchException`.

### “Record có trường `final` nên accessor chắc chắn không lỗi”

Trường component của record là `private final`, nhưng record có thể khai báo accessor tường minh với mã tùy ý hợp lệ. `final` không biến accessor thành phép đọc thuần túy và không cấm unchecked exception.

### “Nếu một record pattern lỗi thì `default` sẽ xử lý”

Không. `default` xử lý trường hợp **không có case áp dụng sau matching bình thường**, không phải một cơ chế `catch`. Lỗi trong accessor làm quá trình matching kết thúc bất thường, cần `try/catch` nếu muốn xử lý.

### “`null` luôn tạo MatchException”

Không. Selector `null` của `switch` có quy tắc riêng; record con `null` khiến mẫu record lồng nhau không khớp; `var` trong record pattern có thể ràng buộc component `null`. Chỉ khi **accessor được gọi và ném exception** thì quy tắc bọc `MatchException` cho lỗi accessor được áp dụng.

### “Chỉ cần bắt `IllegalStateException` để xử lý lỗi accessor”

Nếu `IllegalStateException` được ném **do accessor được gọi trong record pattern**, ngoại lệ đi ra là `MatchException`, còn `IllegalStateException` nằm trong cause. Nếu gọi accessor trực tiếp, chính `IllegalStateException` có thể đi ra. Catch đúng theo đường thực thi thực tế.

### “Lỗi trong `when` cũng luôn bị bọc”

Không. `when` được đánh giá **sau khi pattern khớp**, và lỗi từ phép tính guard không phải lỗi accessor do pattern matching. Trong ví dụ runnable, `IllegalArgumentException` từ guard được bắt trực tiếp.

### “Có thể thêm `throws IOException` vào accessor record”

Không. Java cấm mệnh đề `throws` trên accessor của record, bất kể loại exception viết trong `throws`. Nếu cần xử lý lỗi có kiểm tra, phải thay đổi thiết kế hoặc xử lý bên trong phương thức theo hợp đồng phù hợp.

### “Lỗi này giống mọi `MatchException` khác”

`MatchException` còn có thể biểu thị thất bại khớp bất ngờ ở runtime trong một số cấu trúc đã được chứng minh exhaustive ở compile time (ví dụ khác biệt giữa phiên bản hierarchy lúc biên dịch và lúc chạy). **Khi nguyên nhân là accessor**, `getCause()` chỉ ra ngoại lệ gốc; không nên đoán mọi `MatchException` đều do một accessor cụ thể nếu chưa kiểm tra cause và ngữ cảnh.

## 12. Quy trình chẩn đoán thực tế

Khi gặp `MatchException` quanh record pattern:

1. Xác định nơi đang matching: `instanceof RecordName(...)`, `case RecordName(...)` hoặc một mẫu lồng.
2. Xem **record nào** đang được phân rã và các accessor component nào có thể được gọi.
3. Kiểm tra `ex.getCause()`, thông điệp và stack trace để tìm nơi ném lỗi gốc; đừng chỉ nhìn nhãn `default`.
4. Đối chiếu xem accessor được compiler sinh hay có thân viết tay. Nếu viết tay, kiểm tra điều kiện ném exception, I/O và side effects.
5. Kiểm tra dữ liệu `null`/không hợp lệ: nó khiến mẫu không khớp bình thường, được `var` chấp nhận hay khiến accessor chủ động ném lỗi?
6. Xác định có ngoại lệ đến từ **selector expression**, `when` hoặc thân case hay không; chúng không nhất thiết bị bọc theo cùng quy tắc.
7. Nếu phải bắt lỗi, đặt `try/catch` ở phạm vi bao quanh **đánh giá pattern**, và bảo toàn cause khi ghi log/đưa ra thông báo.
8. Ưu tiên sửa gốc: kiểm định dữ liệu trong constructor, giữ accessor đơn giản, tách thao tác có thể lỗi thành phương thức rõ ràng.
9. Viết regression test cho cả đường hợp lệ và đường bất thường; dùng đúng phiên bản Java để tránh nhầm semantics.

## 13. Bài tập tự kiểm tra

**Bài 1 — Type vs record pattern.** Có `Label bad = new Label(null)` với accessor ở mục 2. `bad instanceof Label label` và `bad instanceof Label(var text)` khác nhau thế nào?

**Đáp án:** type pattern đầu tiên kiểm tra kiểu và có thể khớp mà không gọi `value()`; record pattern thứ hai cần gọi `value()` nên ném `MatchException` với cause `IllegalStateException`.

**Bài 2 — Fallback.** Tại sao `default -> "unknown"` không xử lý khi accessor trong `case Label(var value)` ném lỗi?

**Đáp án:** matching bị kết thúc bất thường, không có quá trình chọn case tiếp theo thông thường. Muốn xử lý thì đặt `try/catch` quanh switch, không dựa vào `default`.

**Bài 3 — Record con null.** Cho `Parcel("P-1", null)`. `Parcel(var id, Label(var text))` có ném `MatchException` vì null không?

**Đáp án:** không. `Label(...)` không khớp record con `null`; mẫu lồng không khớp bình thường. `Parcel(var id, var label)` có thể khớp và `label == null`.

**Bài 4 — Guard.** Nếu `case Label(var text) when check(text)` khớp phần pattern rồi `check(text)` ném `IllegalArgumentException`, có bị bọc thành `MatchException` không?

**Đáp án:** không phải theo quy tắc accessor; ngoại lệ phát sinh khi đánh giá guard lan truyền trực tiếp.

**Bài 5 — Đặt catch.** Catch `MatchException` bên trong block của case có bảo vệ được lỗi từ accessor dùng để quyết định chính case ấy không?

**Đáp án:** không. Accessor có thể lỗi trước khi vào block. Đặt `try/catch` bao quanh toàn bộ `switch` hoặc `instanceof`.

**Bài 6 — Accessor checked exception.** Tại sao `public String code() throws IOException` không hợp lệ trong một record `record R(String code)`?

**Đáp án:** JLS `8.10.3` cấm accessor record có mệnh đề `throws`. Đây là lỗi lúc biên dịch; cần thiết kế lại phần xử lý lỗi, không thể thêm checked exception vào chữ ký accessor.

**Bài 7 — Thiết kế dài hạn.** Với `record SafeLabel(String value)`, muốn cấm giá trị `null` thì nên kiểm tra trong accessor hay compact constructor?

**Đáp án:** thường kiểm tra trong constructor để từ chối dữ liệu ngay khi tạo record, giúp accessor ổn định. Đây là quyết định hợp đồng API; nếu chuyển từ validation muộn sang sớm trong code cũ, cần kiểm thử thay đổi thời điểm ngoại lệ.

**Bài 8 — Cause.** Khi bắt `MatchException ex` từ lỗi accessor, `ex.getCause()` dùng để làm gì?

**Đáp án:** cho biết exception gốc làm accessor kết thúc bất thường, hỗ trợ chẩn đoán. Không được suy luận mọi `MatchException` đều có cùng một cause mà không kiểm tra.

## 14. Ghi nhớ

- Record pattern **gọi accessor của record** để lấy các component cần khớp.
- Accessor tường minh có thể có logic riêng và ném **unchecked exception**, dù chữ ký record accessor **không được chứa `throws`**.
- Nếu accessor ném lỗi trong quá trình pattern matching, Java 21 ném **`MatchException`** và đặt lỗi gốc làm **`cause`**.
- Lỗi này **không phải** việc pattern không khớp; `else`, `default` hoặc case sau không tự bắt được.
- Phân biệt **null selector**, **record con null**, **component null**, lỗi **accessor**, lỗi **guard** và lỗi **thân case**; các trường hợp đó có ngữ nghĩa khác nhau.
- Catch quanh toàn bộ biểu thức/câu lệnh đang matching nếu cần xử lý; đừng đặt catch chỉ trong thân case sẽ không được vào.
- Thiết kế record an toàn bằng cách **kiểm định lúc xây dựng** và giữ accessor **đơn giản, không side effect** khi có thể.
- Dùng ví dụ, kiểm thử và `getCause()` để xác nhận điểm phát sinh lỗi thực sự, thay vì coi mọi exception gần một record pattern là cùng một loại.

**Tài liệu chính thức:**
- [Java Language Specification 21 — Pattern Matching (`14.30.2)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30.2)
- [Java Language Specification 21 — Record Members (`8.10.3)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.10.3)
- [Java SE 21 API — MatchException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/MatchException.html)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
