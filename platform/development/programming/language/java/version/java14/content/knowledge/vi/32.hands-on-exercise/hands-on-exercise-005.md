# Tái cấu trúc kiểm tra kiểu bằng mẫu `instanceof` — thực hành tổng hợp

> **Module Java 14 · Thực hành tổng hợp.** Bài này hướng dẫn chuyển mã Java kiểu cũ `if (value instanceof Type) { Type x = (Type) value; ... }` sang **type pattern** `if (value instanceof Type x) { ... }`, đồng thời bảo toàn hành vi của ứng dụng. **Mốc phiên bản cần phân biệt:** pattern matching for `instanceof` được giới thiệu ở dạng **preview từ Java 14**, thử nghiệm tiếp ở Java 15, rồi **chính thức từ Java 16 (JEP 394)**. Vì ghi chú module yêu cầu chỉ dùng kiến thức còn áp dụng, toàn bộ mã chạy của bài dùng **cú pháp chính thức Java 17+**, biên dịch bằng `javac --release 17`, **không dùng `--enable-preview`, không dựng lại cú pháp preview Java 14**.

## 1. Mục tiêu thực hành

Sau bài này, bạn có thể:

1. Nhận diện cặp thao tác lặp `instanceof` + cast và thay bằng **`instanceof Type variable`**.
2. Giải thích pattern match gồm **kiểm tra kiểu, chuyển kiểu an toàn và gán biến pattern** trong một phép thử.
3. Giữ nguyên logic kinh doanh khi refactor: thứ tự kiểm tra, `null`, trường hợp không khớp, exception, short-circuit và số lần đánh giá biểu thức.
4. Sử dụng đúng **flow scoping** của pattern variable trong nhánh `if`, chuỗi `&&`, phủ định `!` và guard clause.
5. Biết vì sao `if (x instanceof String s || s.isEmpty())` **không biên dịch**, nhưng điều kiện phủ định với `||` có thể hợp lệ.
6. Refactor nhánh kiểm tra nhiều kiểu, collection `List<?>`, override `equals(Object)` và một bộ phân loại thông điệp thực tế.
7. Viết kiểm thử hành vi **trước/sau** với dữ liệu bình thường, rỗng, sai kiểu và `null`.
8. Tránh các trường hợp không hợp lệ khi compile: kiểm tra một type pattern vốn đã đúng theo kiểu tĩnh, generic không reifiable, dùng biến ngoài phạm vi.
9. Hiểu phạm vi tính năng: **type pattern cho `instanceof`** khác **record pattern** và **pattern matching for `switch`** được chính thức hóa sau này.
10. Biết khi nào không nên thay cả hệ thống bằng nhiều nhánh `instanceof`, mà nên thiết kế **polymorphism**, sealed hierarchy hoặc pattern switch phù hợp.

## 2. Bối cảnh và phiên bản — chỉ dùng cách viết hiện hành

| Phiên bản | Trạng thái liên quan | Ý nghĩa khi thực hành hôm nay |
| --- | --- | --- |
| Java 14 | `instanceof` type patterns **preview** (JEP 305) | Mốc lịch sử của module, **không dùng `--enable-preview` của Java 14 để học cú pháp hiện hành**. |
| Java 15 | Second preview (JEP 375) | Không phải target khuyến nghị của bài. |
| **Java 16** | **Tính năng chính thức** (JEP 394) | `instanceof Type variable` dùng không cần preview; pattern variables không còn mặc nhiên `final`. |
| Java 17 | Ngôn ngữ có type patterns chính thức; bản LTS phổ biến | **Target của các ví dụ độc lập**, `javac --release 17`. |
| Java 21 | Pattern matching for `switch` và record patterns chính thức (JEP 441/440) | Có thể dùng cho bài toán khác, **không cần để refactor `instanceof` trong bài này**. |
| JDK 25 | Tài liệu ngôn ngữ hiện hành tiếp tục mô tả `instanceof` type patterns | Có thể tham khảo API/JLS, nhưng các ví dụ dùng **subset đã chính thức ở Java 17**. |

`instanceof` cũ và type-pattern `instanceof` **đều tiếp tục hợp lệ**. “Mã cũ” trong bài chỉ có nghĩa là **cách viết cần cast thủ công, dài và dễ lệch giữa kiểm tra/cast**, không phải Java cấm dùng `instanceof Type` truyền thống.

### Ví dụ ba bước so với một bước

Trước:

~~~java
if (candidate instanceof String) {
    String text = (String) candidate;
    System.out.println(text.length());
}
~~~

Sau:

~~~java
if (candidate instanceof String text) {
    System.out.println(text.length());
}
~~~

Đây là **mảnh code**, giả định `candidate` có kiểu `Object` hoặc một kiểu tham chiếu phù hợp. Ở bản sau:

- `String` là **type** được kiểm tra.
- `text` là **pattern variable** có kiểu `String`.
- Nếu target là một `String` không null, phép thử thành công và biến `text` được gán đối tượng đã kiểm tra.
- Nếu không khớp, nhánh không chạy và `text` không nằm trong scope nơi chưa chắc chắn pattern thành công.
- Không phải viết cast thủ công, vì compiler đã có bằng chứng kiểu của `text`.

Không có “magic conversion” từ `Integer` sang chuỗi: `candidate instanceof String text` chỉ kiểm tra **quan hệ kiểu runtime**, không gọi `toString()` hay parser để tạo chuỗi mới.

## 3. Quy trình refactor an toàn theo từng bước

Một migration đáng tin không chỉ là tìm và thay token:

1. **Ghi nhận contract trước khi sửa:** input có thể `null` không? Các kiểu con nào đang được chấp nhận? Thứ tự `if/else if` có ý nghĩa không?
2. **Tìm cặp kiểu tương ứng:** `if (x instanceof T) { T value = (T) x; ... }`. Kiểm tra `x` ở hai vị trí có thực sự là **cùng giá trị/biểu thức**.
3. **Chọn tên pattern variable mô tả vai trò**: `text`, `order`, `items`, `amount`; tránh đặt `o`/`t` tùy tiện trong mã nghiệp vụ.
4. **Thay một nhánh trước:** `if (x instanceof T value)`, bỏ declaration/cast cũ, không đổi logic business.
5. **Di chuyển điều kiện phụ cẩn thận:** có thể ghép bằng `&&` khi scope bảo đảm; không đổi các biểu thức có side effect hoặc thứ tự đánh giá.
6. **Kiểm tra flow scoping:** pattern variable chỉ dùng nơi compiler chứng minh match đã xảy ra; xử lý guard `return` đúng.
7. **Kiểm tra generics:** dùng reifiable pattern như `List<?>`, không dùng `List<String>` để kiểm tra kiểu tham số đã bị type erasure.
8. **So kết quả trước/sau** trên đủ tập dữ liệu có `null`, kiểu không khớp, collection rỗng, điều kiện biên.
9. **Chạy compile/tests ở minimum supported JDK** của sản phẩm, không chỉ trên máy dùng JDK mới nhất.
10. **Review diff:** loại cast thừa nhưng không vô tình thay exception, thứ tự nhánh, log, giá trị trả về hoặc số lần gọi hàm.

**Mục tiêu:** cải thiện sự rõ ràng và an toàn kiểu, **không mặc định có lợi ích hiệu năng**. Chỉ có benchmark/profiler mới chứng minh được chênh lệch runtime trên workload cụ thể.

## 4. Bài thực hành chính — phân loại payload trước/sau refactor

Giả sử một service nhận payload dạng `Object`: một chuỗi văn bản, một số nguyên, danh sách chứa nhiều kiểu, `null` hoặc loại không hỗ trợ. Contract hiện tại:

- `String` không trắng: trả `text:` cùng văn bản đã `strip()`.
- `Integer >= 0`: trả `count:` cùng số nguyên.
- `List<?>`: trả `list:N:nonBlank=M`, đếm các phần tử là `String` không blank.
- `null`: trả `null`.
- Các trường hợp còn lại: `unsupported:` cộng tên lớp runtime.

Đây là bài toán tốt để **chỉ refactor cast**, không thay bất cứ policy nào. Đặc biệt: chuỗi toàn khoảng trắng và Integer âm sẽ đi vào fallback; **đó là contract đang xét**, không phải tính năng của pattern.

### Ví dụ độc lập 1 — Hai phiên bản, đối chiếu kết quả tự động

Tạo file **`PayloadRefactorDemo.java`**:

~~~java
import java.util.List;

public class PayloadRefactorDemo {
    static String before(Object payload) {
        if (payload instanceof String) {
            String text = (String) payload;
            if (!text.isBlank()) {
                return "text:" + text.strip();
            }
        }

        if (payload instanceof Integer) {
            Integer number = (Integer) payload;
            if (number >= 0) {
                return "count:" + number;
            }
        }

        if (payload instanceof List<?>) {
            List<?> items = (List<?>) payload;
            int count = 0;
            for (Object item : items) {
                if (item instanceof String) {
                    String text = (String) item;
                    if (!text.isBlank()) {
                        count++;
                    }
                }
            }
            return "list:" + items.size() + ":nonBlank=" + count;
        }

        if (payload == null) {
            return "null";
        }
        return "unsupported:"
                + payload.getClass().getSimpleName();
    }

    static String after(Object payload) {
        if (payload instanceof String text && !text.isBlank()) {
            return "text:" + text.strip();
        }

        if (payload instanceof Integer number && number >= 0) {
            return "count:" + number;
        }

        if (payload instanceof List<?> items) {
            int count = 0;
            for (Object item : items) {
                if (item instanceof String text && !text.isBlank()) {
                    count++;
                }
            }
            return "list:" + items.size() + ":nonBlank=" + count;
        }

        if (payload == null) {
            return "null";
        }
        return "unsupported:"
                + payload.getClass().getSimpleName();
    }

    public static void main(String[] args) {
        Object[] samples = {
            "  Java  ",
            Integer.valueOf(3),
            List.of("A", 1, " ", " B "),
            null,
            Integer.valueOf(-4)
        };

        for (Object input : samples) {
            String oldResult = before(input);
            String newResult = after(input);
            System.out.println(newResult + " | same="
                    + oldResult.equals(newResult));
        }
    }
}
~~~

Biên dịch/chạy với JDK 17+:

~~~bash
javac --release 17 PayloadRefactorDemo.java
java PayloadRefactorDemo
~~~

**Stdout dự kiến, không phụ thuộc môi trường:**

~~~text
text:Java | same=true
count:3 | same=true
list:4:nonBlank=2 | same=true
null | same=true
unsupported:Integer | same=true
~~~

### Phân tích từng thay đổi

**Nhánh String:** bản cũ kiểm tra `payload instanceof String`, cast sang `String text`, rồi kiểm tra `!text.isBlank()`. Bản mới gộp thành `payload instanceof String text && !text.isBlank()`. `&&` đánh giá vế phải **chỉ khi vế trái true**, vì thế `text` đã được gán trước khi dùng `isBlank()`.

**Nhánh Integer:** `number` ở mẫu mới có kiểu `Integer`. So sánh `number >= 0` thực hiện unboxing một giá trị không null đã match kiểu; hợp đồng giống bản cũ.

**Nhánh List:** `payload instanceof List<?> items` chỉ chứng minh payload là một `List` runtime; nó **không xác nhận mỗi phần tử là String**. Vòng `for` vẫn cần kiểm tra từng `Object item instanceof String text` trước khi gọi `isBlank()`.

**Null:** cả cách cũ và mới đều có `instanceof` trả `false` với `null`. Không branch nào dereference `null`; sau đó trả chuỗi `"null"`.

**Fallback:** giữ nguyên tên lớp và thứ tự điều kiện. Nếu định đổi policy cho số âm hoặc chuỗi blank, hãy coi đó là **thay đổi nghiệp vụ riêng**, không “lén” đưa vào commit refactor.

### Vì sao không nên đổi `if` thành `else if` tùy tiện?

Trong ví dụ này, do mỗi nhánh thành công đều `return` và những kiểu cơ bản không chồng lấn giữa `String`/`Integer`/`List`, bạn có thể dùng `else if` mà không đổi kết quả. Nhưng một codebase khác có thể cho phép **nhiều nhánh xử lý trên cùng đối tượng** (ví dụ các interfaces giao nhau) hoặc có side effects. Không chuyển toàn bộ các `if` thành `else if` nếu chưa kiểm chứng semantics.

### Vì sao bài tập không dùng `case String text -> ...`?

Pattern switch đã chính thức trong Java 21; đây là **bài riêng**. Nhiệm vụ ở hàng này là **tái cấu trúc các phép kiểm tra kiểu bằng type pattern của `instanceof`** đã chính thức Java 16. Giữ trọng tâm `instanceof` làm bài chạy được trên Java 17 mà không cần source level 21.

## 5. Flow scoping: biến pattern có hiệu lực ở đâu?

Biến thông thường có phạm vi từ khai báo theo lexical scope; với pattern variable, compiler còn xét **khả năng nhánh điều khiển đã chứng minh phép match thành công** (*flow scoping*).

~~~java
Object candidate = "hello";

if (candidate instanceof String text) {
    System.out.println(text.length()); // Hợp lệ.
} else {
    // text KHÔNG ở trong scope này.
}
// text cũng không luôn ở trong scope sau if.
~~~

Đây là mảnh code. Bản chất không phải compiler “tự cast mọi nơi”, mà là biến `text` chỉ được dùng nơi phép match đã thành công và biến được gán chắc chắn.

### Flow scoping với `&&`

Hợp lệ:

~~~java
if (candidate instanceof String text && text.length() > 3) {
    System.out.println(text.toUpperCase());
}
~~~

Khi vế phải của `&&` được đánh giá, vế trái chắc chắn true; pattern variable tồn tại. Với `&` (toán tử AND không short-circuit), không suy diễn y hệt; hãy dùng `&&` cho kiểu guard này.

### Guard clause với phủ định

Hợp lệ và thường làm code phẳng hơn:

~~~java
static int lengthOrMinusOne(Object input) {
    if (!(input instanceof String text)) {
        return -1;
    }
    return text.length(); // Đến đây pattern chắc chắn match.
}
~~~

Mảnh phương thức trên cho thấy `text` vẫn dùng được **sau `if`**, vì nhánh không match đã kết thúc bằng `return`. Nếu nhánh thất bại vẫn có thể tiếp tục chạy, compiler không thể cho bạn dùng `text` ngoài phạm vi được bảo đảm.

### Với `||`: vấn đề không phải dấu OR, mà là điều kiện flow

**Sai, không biên dịch:**

~~~java
if (candidate instanceof String text || text.isEmpty()) {
    // Lỗi: ở vế phải, pattern có thể không match.
}
~~~

`||` đánh giá vế phải khi vế trái **false**, lúc đó không có `text` được gán. Nhưng phủ định có thể tạo điều kiện hợp lệ:

~~~java
if (!(candidate instanceof String text) || text.isBlank()) {
    return "invalid";
}
return text.strip();
~~~

Đây là **mảnh phương thức trả String**, giả định `candidate` được khai báo. Trong vế phải của `||` ở phiên bản phủ định, vế trái là **false**, nghĩa là `candidate instanceof String text` đã **true**, nên `text` hợp lệ. Sau `if`, mọi đường đi tiếp tục đều có text đã match. Dù đúng, với code nhiều người bảo trì, có thể chọn hai guard clauses riêng nếu dễ đọc hơn.

## 6. Ví dụ độc lập 2 — Guard clause, null và scope

Tạo **`GuardScopeDemo.java`**:

~~~java
import java.util.Locale;

public class GuardScopeDemo {
    static String describe(Object input) {
        if (!(input instanceof String text)) {
            return "not-text";
        }

        String normalized = text.strip();
        if (normalized.isEmpty()) {
            return "blank";
        }
        return "text:" + normalized.toUpperCase(Locale.ROOT);
    }

    public static void main(String[] args) {
        System.out.println(describe("  hi  "));
        System.out.println(describe("  "));
        System.out.println(describe(null));
        System.out.println(describe(Integer.valueOf(7)));
    }
}
~~~

Chạy:

~~~bash
javac --release 17 GuardScopeDemo.java
java GuardScopeDemo
~~~

**Stdout chính xác:**

~~~text
text:HI
blank
not-text
not-text
~~~

- `null` không match `String`, nên `describe(null)` trả `not-text` mà không ném `NullPointerException`.
- Input `"  "` match kiểu String, nhưng bị từ chối ở validation nội dung; **type check không thay thế validation**.
- `normalized` là biến thường tạo ra giá trị đã biến đổi; `text` giữ nguyên đối tượng đã match. Pattern variable có thể được gán lại ở Java 16+, nhưng không nhất thiết nên làm vậy trong refactor.

## 7. Ví dụ độc lập 3 — `&&` và `||` hợp lệ

Tạo **`BooleanScopeDemo.java`**:

~~~java
import java.util.Locale;

public class BooleanScopeDemo {
    static String validate(Object input) {
        if (!(input instanceof String text) || text.isBlank()) {
            return "invalid";
        }
        return "ok:" + text.strip();
    }

    static String describe(Object input) {
        if (input instanceof String text && text.length() >= 3) {
            return "long:" + text.toUpperCase(Locale.ROOT);
        }
        if (input instanceof Integer number && number >= 3) {
            return "int:" + number;
        }
        return "other";
    }

    public static void main(String[] args) {
        System.out.println("validate1=" + validate("  hi  "));
        System.out.println("validate2=" + validate(" "));
        System.out.println("validate3=" + validate(null));
        System.out.println("describe1=" + describe("abcd"));
        System.out.println("describe2=" + describe(Integer.valueOf(5)));
        System.out.println("describe3=" + describe("a"));
    }
}
~~~

Chạy:

~~~bash
javac --release 17 BooleanScopeDemo.java
java BooleanScopeDemo
~~~

**Stdout chính xác:**

~~~text
validate1=ok:hi
validate2=invalid
validate3=invalid
describe1=long:ABCD
describe2=int:5
describe3=other
~~~

Ở `validate`, vế phải `text.isBlank()` của `||` chỉ được thực thi khi **`!(input instanceof String text)` là false**; tức input đã match `String` và biến `text` chắc chắn được gán. Ở `describe`, cả hai phép `&&` chỉ gọi method trên biến pattern sau khi match true.

### Cảnh báo đổi logic khi ghép điều kiện

Trước:

~~~java
if (value instanceof String) {
    String text = (String) value;
    if (text.length() > 3) {
        use(text);
    }
}
~~~

Sau:

~~~java
if (value instanceof String text && text.length() > 3) {
    use(text);
}
~~~

Đây là hai **mảnh code**, giả định có `value` và `use`. Chúng có thể tương đương nếu không có side effect ẩn và không có `else` gắn với `if` bên trong. Nếu bản cũ có `else` để xử lý String ngắn, chuyển thành một `if` mới có thể đánh mất nhánh đó. **Tái cấu trúc phải bảo toàn toàn bộ control flow, không chỉ nhánh true.**

## 8. Biểu thức bên trái chỉ được đánh giá một lần

Một lỗi trong mã cast thủ công thường xảy ra khi programmer **gọi lại một phương thức** thay vì cast cùng giá trị đã kiểm tra.

**Rủi ro trong code cũ:**

~~~java
if (nextValue() instanceof String) {
    String text = (String) nextValue();
    // nextValue() được gọi lần thứ hai!
}
~~~

Đây là **mảnh code cố ý minh họa lỗi**. Nếu `nextValue()` đọc queue, tăng counter, lấy item khác hoặc trạng thái thay đổi, lần gọi thứ hai có thể trả **một loại khác**, dẫn tới `ClassCastException` hoặc dữ liệu sai.

**Cách an toàn với pattern** (hoặc lưu một local snapshot trước khi kiểm tra):

~~~java
if (nextValue() instanceof String text) {
    // text được gán từ chính kết quả của lần gọi đã kiểm tra.
    System.out.println(text);
}
~~~

### Ví dụ độc lập 4 — Kiểm chứng đánh giá một lần

Tạo **`SingleEvaluationDemo.java`**:

~~~java
public class SingleEvaluationDemo {
    private static int reads;

    static Object nextValue() {
        reads++;
        return reads == 1 ? "first" : Integer.valueOf(99);
    }

    public static void main(String[] args) {
        if (nextValue() instanceof String text) {
            System.out.println("matched=" + text);
        }
        System.out.println("reads=" + reads);
    }
}
~~~

Chạy:

~~~bash
javac --release 17 SingleEvaluationDemo.java
java SingleEvaluationDemo
~~~

**Stdout chính xác:**

~~~text
matched=first
reads=1
~~~

Pattern matching không “gọi lại” expression để cast. Với code cũ, giải pháp bảo toàn nghĩa cũng có thể là:

~~~java
Object snapshot = nextValue();
if (snapshot instanceof String) {
    String text = (String) snapshot;
}
~~~

Đây là **mảnh code**. Khi refactor một biểu thức có side effects, hãy bảo đảm hành vi mong muốn là **chỉ đọc một lần**; đừng tự viết thêm một lần gọi ở chỗ khác khi di chuyển code.

### Biến pattern không làm đối tượng bất biến

`String text` là một tham chiếu kiểu String, nhưng với pattern như `List<?> items` hoặc kiểu mutable tự định nghĩa, bạn vẫn có thể sửa trạng thái bên trong đối tượng thông qua các method của nó. Pattern variable **không tự sao chép object**, không cung cấp snapshot deep copy hoặc thread safety.

## 9. Generic collections và type erasure

**Không hợp lệ:**

~~~java
Object value = java.util.List.of("a", "b");
if (value instanceof java.util.List<String> texts) {
    // Lỗi: List<String> không reifiable.
}
~~~

Đây là **code cố ý không biên dịch**. Java generics sử dụng **type erasure**, runtime không đủ thông tin để xác nhận mọi element có đúng type parameter `String` chỉ bằng `instanceof List<String>`.

**Hợp lệ:**

~~~java
if (value instanceof java.util.List<?> items) {
    for (Object item : items) {
        if (item instanceof String text) {
            System.out.println(text);
        }
    }
}
~~~

Đây là **mảnh code hợp lệ**, với `value` kiểu `Object`. `List<?>` kiểm tra **raw container runtime type** với wildcard reifiable; sau đó cần kiểm tra từng element trước khi sử dụng như String.

### Ví dụ độc lập 5 — Duyệt list nhiều kiểu

Tạo **`GenericItemsDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class GenericItemsDemo {
    static String stringsIn(Object value) {
        if (!(value instanceof List<?> items)) {
            return "not-list";
        }

        List<String> strings = new ArrayList<>();
        for (Object element : items) {
            if (element instanceof String text) {
                strings.add(text);
            }
        }
        return strings.toString();
    }

    public static void main(String[] args) {
        System.out.println(stringsIn(List.of("A", 7, "B")));
        System.out.println(stringsIn(List.of()));
        System.out.println(stringsIn(null));
    }
}
~~~

Chạy:

~~~bash
javac --release 17 GenericItemsDemo.java
java GenericItemsDemo
~~~

**Stdout chính xác:**

~~~text
[A, B]
[]
not-list
~~~

Một `List<?>` có thể chứa Integer, null, String hoặc các đối tượng khác tùy implementation; ví dụ `List.of(...)` không nhận null, nhưng phương thức `stringsIn` vẫn phải coi collection từ bên ngoài là không đồng nhất. `instanceof String text` tự động bỏ qua element `null` vì phép thử false.

**Chú ý:** dùng `List<?>` chỉ xác minh runtime instance implements List. Nếu nghiệp vụ đòi danh sách chỉ chứa String, phải **validate tất cả phần tử** hoặc định nghĩa data contract/type-safe boundary từ trước, không chỉ lọc phần tử String như demo.

## 10. Refactor `equals(Object)` gọn và an toàn

`equals(Object)` là một use case kinh điển vì tham số có kiểu `Object`, ta thường kiểm tra kiểu trước khi so fields.

**Trước:**

~~~java
@Override
public boolean equals(Object other) {
    if (this == other) {
        return true;
    }
    if (!(other instanceof Token)) {
        return false;
    }
    Token token = (Token) other;
    return java.util.Objects.equals(value, token.value);
}
~~~

**Sau:**

~~~java
@Override
public boolean equals(Object other) {
    return this == other
            || (other instanceof Token token
                && java.util.Objects.equals(value, token.value));
}
~~~

Đây là hai mảnh method cùng contract khi được đặt trong một class `Token` có field `value` kiểu String. `this == other` xử lý cùng instance; nếu khác instance thì `instanceof Token token` kiểm tra/giữ biến kiểu Token. `other == null` -> false, không ném exception.

### Ví dụ độc lập 6 — `equals` và `hashCode`

Tạo **`TokenEqualsDemo.java`**:

~~~java
import java.util.Objects;

public class TokenEqualsDemo {
    static final class Token {
        private final String value;

        Token(String value) {
            this.value = value;
        }

        @Override
        public boolean equals(Object other) {
            return this == other
                    || (other instanceof Token token
                    && Objects.equals(value, token.value));
        }

        @Override
        public int hashCode() {
            return Objects.hashCode(value);
        }
    }

    public static void main(String[] args) {
        Token first = new Token("A");
        Token same = new Token("A");
        Token different = new Token("B");

        System.out.println("equal=" + first.equals(same));
        System.out.println("different=" + first.equals(different));
        System.out.println("null=" + first.equals(null));
        System.out.println("self=" + first.equals(first));
        System.out.println("hashEqual="
                + (first.hashCode() == same.hashCode()));
    }
}
~~~

Chạy:

~~~bash
javac --release 17 TokenEqualsDemo.java
java TokenEqualsDemo
~~~

**Stdout chính xác:**

~~~text
equal=true
different=false
null=false
self=true
hashEqual=true
~~~

**Quan trọng:** refactor `equals` không được thay định nghĩa equality giữa các classes. Với inheritance, `getClass() == other.getClass()` và `instanceof` có semantics khác nhau; thay `getClass` bằng `instanceof` có thể phá tính đối xứng/transitivity của equals. Demo dùng **`final class Token`**, nên những rủi ro subtype phức tạp không xuất hiện. Nếu original code bắt buộc đúng runtime class, đừng tùy tiện đổi behavior.

Khi override `equals`, vẫn phải tuân thủ hợp đồng `hashCode`: các object equal phải có hash code bằng nhau. Pattern matching không tự tạo `hashCode`. Nếu entity có nhiều fields, kiểm tra null-safe equality và hash phù hợp.

## 11. Kiểm tra kiểu trong một hierarchy hiện đại

Trong một mô hình dữ liệu rõ ràng, pattern variables giúp xử lý nhánh type-specific mà không cần cast tay. Có thể áp dụng với **record** (chính thức từ Java 16) và **sealed interface** (chính thức từ Java 17), đều là tính năng ổn định trên target bài này.

### Ví dụ độc lập 7 — Điều phối event với type patterns

Tạo **`EventRouterDemo.java`**:

~~~java
public class EventRouterDemo {
    sealed interface Event permits TextEvent, CountEvent { }

    record TextEvent(String text) implements Event { }

    record CountEvent(int count) implements Event { }

    static String route(Event event) {
        if (event instanceof TextEvent textEvent) {
            return "text:" + textEvent.text();
        }
        if (event instanceof CountEvent countEvent) {
            return "count:" + countEvent.count();
        }
        return "none";
    }

    public static void main(String[] args) {
        System.out.println(route(new TextEvent("hello")));
        System.out.println(route(new CountEvent(4)));
        System.out.println(route(null));
    }
}
~~~

Chạy:

~~~bash
javac --release 17 EventRouterDemo.java
java EventRouterDemo
~~~

**Stdout chính xác:**

~~~text
text:hello
count:4
none
~~~

Mặc dù `TextEvent` và `CountEvent` là **record**, các pattern trên vẫn chỉ là **type patterns** (`instanceof TextEvent textEvent`), **không phải record deconstruction patterns** như cú pháp `instanceof TextEvent(String text)` được chính thức trong Java 21.

**Giới hạn:** sealed hierarchy có tập subtype xác định, nhưng chuỗi `if` trong ví dụ **không được compiler kiểm tra exhaustiveness theo cùng cách một số pattern switch expressions được kiểm tra**. Nhánh `return "none"` vẫn xử lý `null` hoặc trường hợp không khớp. Với logic dispatch lớn, cân nhắc **polymorphism** hoặc pattern switch Java 21+ ở bước thiết kế riêng; đừng đưa vào refactor chỉ vì muốn xóa cast.

## 12. Biến pattern không còn mặc nhiên `final` — nhưng có nên gán lại?

Trong preview ban đầu, pattern variables có hạn chế khác. **Java 16** khi chuẩn hóa JEP 394 đã bỏ quy tắc **“pattern variable luôn implicitly final”**. Vì vậy với Java 17, ví dụ:

~~~java
if (value instanceof String text) {
    text = text.strip();
    System.out.println(text);
}
~~~

là mảnh code có thể biên dịch (giả định `value` có kiểu tham chiếu thích hợp). Nhưng khi review một refactor, việc gán lại pattern variable có thể làm khó phân biệt giữa **giá trị được kiểm tra** và **giá trị đã chuyển đổi**. Thường nên giữ:

~~~java
if (value instanceof String text) {
    String normalized = text.strip();
    System.out.println(normalized);
}
~~~

Nếu pattern variable được capture bởi lambda, quy tắc **effectively final** của Java vẫn áp dụng như với local variables. Một pattern variable bị gán lại sẽ không còn effectively final; đừng dựa vào mô tả cũ “pattern variables luôn final” hoặc tuyên bố từ Java 16 có thể thay đổi nó tùy ý trong lambda.

### Nên đặt tên biến pattern thế nào?

- Tốt: `input instanceof Customer customer`, `node instanceof BlockTree block`, `payload instanceof String text`.
- Cần cân nhắc: `input instanceof Customer c` trong hàm nhiều nhánh, vì tên `c` kém rõ nghĩa.
- Không dùng tên đã có variable trong scope gây xung đột; compiler còn áp dụng quy tắc shadowing/flow-scoping.
- Các nhánh `if/else if` có thể tái sử dụng tên pattern khi scopes không giao nhau, nhưng tên thể hiện domain thường làm code dễ hiểu hơn.

## 13. Các giới hạn compile-time cần nhận diện

### 13.1. Biểu thức có kiểu tĩnh đã là subtype của pattern type

JEP 394 đưa vào lỗi compile-time cho phép thử type pattern vô nghĩa khi biểu thức tĩnh `S` đã là subtype của pattern type `T`.

**Sai trên Java 17:**

~~~java
String alreadyString = "hello";
if (alreadyString instanceof String text) {
    System.out.println(text);
}
~~~

Đây là **mảnh code cố ý không biên dịch** vì kiểm tra `String` → `String` với pattern không cung cấp thông tin kiểu mới. Nếu đã có biến `String`, dùng trực tiếp:

~~~java
String text = "hello";
System.out.println(text);
~~~

Nếu input thực sự thuộc kiểu rộng hơn như `Object` hoặc interface cha, pattern test có ý nghĩa:

~~~java
Object candidate = "hello";
if (candidate instanceof String text) {
    System.out.println(text);
}
~~~

**Không sửa lỗi bằng cách cast lên `Object` chỉ để ép compiler chấp nhận pattern** nếu bài toán không cần kiểm tra kiểu: đó là thêm mã thừa, che giấu vấn đề thiết kế.

### 13.2. Generic type parameter bị xóa

**Sai:**

~~~java
Object candidate = java.util.List.of("x");
if (candidate instanceof java.util.List<String> items) {
    // Type parameter String không được runtime xác minh.
}
~~~

Dùng `List<?>` rồi kiểm tra từng element, hoặc kiểm soát type ở boundary trước khi chuyển sang `Object`.

### 13.3. Sử dụng biến pattern ở nhánh có thể chưa match

**Sai:**

~~~java
if (value instanceof String text || text.isEmpty()) {
    // text có thể chưa tồn tại ở vế phải.
}
~~~

**Sai:**

~~~java
if (value instanceof String text) {
    use(text);
}
use(text); // Không chắc pattern matched.
~~~

Đây là các mảnh code **cố ý không compile**. Đặt sử dụng trong vùng compiler chứng minh `instanceof` đã true, hoặc dùng guard clause kết thúc khi không match.

### 13.4. Không có pattern `instanceof int n` trong target Java 17

Type pattern của `instanceof` chính thức trong Java 17 dùng kiểu tham chiếu. Ví dụ `Object value = 5` thực tế chứa `Integer` do boxing; hãy kiểm tra `value instanceof Integer n`. Không thay vào đó bằng cú pháp primitive pattern thuộc các đề xuất/giai đoạn preview của các JDK muộn hơn; bài này chỉ dùng tính năng đã chính thức và ổn định.

### 13.5. `instanceof` không giải quyết subtype dominance trong chains

Nếu input có kiểu `Object`, cả `Integer` và `Number` có thể match khi object thực sự là Integer. Vì vậy:

~~~java
if (value instanceof Number number) {
    // Integer cũng vào đây.
} else if (value instanceof Integer integer) {
    // Nhánh này không chạy đối với Integer.
}
~~~

Đây là mảnh code có thể gây **dead branch về mặt logic**. Hãy xếp điều kiện từ **kiểu cụ thể hơn** đến **kiểu bao quát hơn** khi đó là ý định của domain, hoặc thay bằng polymorphism nếu nhiều kiểu con.

Không cần thay order trong một refactor “chỉ bỏ cast” nếu việc đổi thứ tự làm thay đổi kết quả; tách việc tối ưu branch order thành thay đổi có test riêng.

## 14. Refactor phải bảo toàn ngoại lệ, side effects và số lần đánh giá

Một phép biến đổi an toàn thông thường:

~~~java
Object snapshot = source.read();
if (snapshot instanceof Customer) {
    Customer customer = (Customer) snapshot;
    process(customer);
}
~~~

thành:

~~~java
Object snapshot = source.read();
if (snapshot instanceof Customer customer) {
    process(customer);
}
~~~

Hai đoạn đều là mảnh code giả định `source`, `Customer`, `process` đã được định nghĩa. Chúng đánh giá `source.read()` **một lần**. Nhưng nếu bạn gộp và di chuyển thêm calls hoặc logging, có thể vô ý đổi flow.

Đừng tự động biến:

~~~java
if (source.read() instanceof Customer) {
    Customer customer = (Customer) source.read();
    process(customer);
}
~~~

thành pattern matching rồi tuyên bố behavior hoàn toàn tương đương **trong mọi trường hợp**: bản cũ đánh giá `source.read()` **hai lần**, còn bản mới một lần. Đây thường là **sửa bug đáng mong muốn**, nhưng phải được ghi nhận như behavior change và test với các nguồn dữ liệu có side effects.

### Những yếu tố cần so trước/sau

| Điều kiện | Rủi ro nếu đổi thiếu kiểm chứng |
| --- | --- |
| Input `null` | Nhánh fallback hoặc exception behavior thay đổi. |
| Biểu thức được gọi lặp | Số lần thực thi side effects khác nhau. |
| Order giữa `String`, `CharSequence`, `Object` | Nhánh được chọn thay đổi khi kiểu chồng lấn. |
| `if` độc lập vs `else if` | Một đối tượng có thể/không thể xử lý nhiều nhánh. |
| Kết hợp `&&`/`||` | Short-circuit và scope bị thay đổi. |
| Biến mutable hoặc concurrent access | Snapshot và giá trị tại thời điểm check khác nhau. |
| Early `return`/`throw` | Đường điều khiển và lỗi được quan sát khác nhau. |
| Cast và kiểm tra khác biểu thức | Dễ bỏ sót lỗi hoặc thay hành vi ngoại lệ. |
| Logging/metrics side effects | Số lần ghi log/counter có thể thay. |
| Domain validation | Type match **không** xác nhận giá trị hợp lệ. |

Một refactor chuyên nghiệp cần **test characterization** trước, thực hiện thay đổi cơ học, rồi test lại; nếu chủ động sửa behavior, nói rõ trong mô tả thay đổi.

## 15. Khi nào không nên thêm quá nhiều `instanceof`?

Type patterns giúp code hiện có ngắn và an toàn hơn, nhưng một chuỗi dài 30 nhánh `instanceof` không nhất thiết là kiến trúc tốt.

**Cân nhắc polymorphism nếu:**

- Các class cùng một interface cung cấp cùng hành vi, ví dụ `Event.handle()`.
- Mỗi lần thêm subtype lại phải sửa nhiều chỗ.
- Quy tắc xử lý là trách nhiệm tự nhiên của từng object.
- Có thể tránh được central type-dispatch mà không làm interface phình to.

**Cân nhắc pattern switch Java 21+ nếu:**

- Mọi case được xử lý theo một taxonomy rõ (sealed types, records).
- Bạn cần match nhiều dạng dữ liệu với cấu trúc case dễ đọc và exhaustiveness khi áp dụng.
- Minimum Java của ứng dụng **thực sự >= 21**.
- Bài toán yêu cầu các tính năng đã chính thức ở Java 21, không preview.

**Giữ `instanceof` type patterns nếu:**

- Đang sửa một method nhỏ có vài nhánh type checks.
- Đối tượng đến từ API tổng quát `Object`/third-party mà bạn không kiểm soát hierarchy.
- Kiểm tra/điều kiện tại boundary như `equals(Object)` hoặc parser/adapter.
- Việc nâng minimum JDK lên 21 không nằm trong phạm vi dự án.

Không nên đổi mọi thứ sang visitor/pattern switch chỉ vì có cú pháp mới: **lựa chọn cấu trúc phải dựa vào độ phức tạp và contract của domain**.

## 16. Kiểm thử hồi quy có hệ thống

### Bộ ca bắt buộc khi refactor

| Nhóm | Input | Điều cần so |
| --- | --- | --- |
| Null | `null` | Không lỗi bất ngờ; fallback đúng. |
| Type match | `"Java"` với `String` | Vào đúng nhánh, giá trị không đổi. |
| Type mismatch | `Integer.valueOf(1)` với `String` | Không cast; fallback đúng. |
| Empty/blank | `""`, `"   "` | Không gộp type check với validation sai cách. |
| Generic list | `List.of("A", 1)` | Chỉ String elements được xử lý nếu contract yêu cầu. |
| List rỗng | `List.of()` | Không tạo lỗi hoặc giả định phần tử đầu tiên. |
| Subtype | `Integer` khi có nhánh `Number` | Branch order không đổi. |
| Side-effect source | Getter/iterator sinh giá trị mới | Giữ đúng số lần đánh giá, trừ khi chủ động sửa bug. |
| Exception | Unsupported type/domain error | Giữ loại lỗi và nội dung nghiệp vụ khi cần. |
| Equals | Cùng instance, equal instance, khác instance, null | Symmetry/reflexivity/hash contract. |
| Concurrent mutation | Input có thể thay giữa các calls | Chụp snapshot/đồng bộ đúng nếu cần. |

### Tự kiểm tra without JUnit

Trong `PayloadRefactorDemo`, lặp qua `Object[] samples`, gọi `before` và `after` rồi so `oldResult.equals(newResult)`. Nếu một sample in `same=false`, đây là tín hiệu **không được xem refactor là behavior-preserving**. Trong một CI test thật, hãy thay việc in bằng assertions ném `AssertionError` nếu khác nhau.

Ví dụ mảnh test:

~~~java
static void assertSame(Object input) {
    String expected = before(input);
    String actual = after(input);
    if (!java.util.Objects.equals(expected, actual)) {
        throw new AssertionError(
                "Mismatch: expected=" + expected + ", actual=" + actual);
    }
}
~~~

Hàm trên là **mảnh code** dùng trong cùng class có `before`/`after`. Dùng `Objects.equals` để so an toàn cả khi một implementation có thể trả `null`; bản demo chính trả String không null.

### Nếu dự án dùng JUnit 5

Kiểm thử với `org.junit.jupiter.api.Assertions.assertEquals` có thể dạng:

~~~java
assertEquals(before(sample), after(sample));
~~~

Đây là **mảnh test**, cần thêm JUnit Jupiter dependency và imports riêng. Không phải chương trình độc lập chỉ với `javac`/`java`; bài đã có các demo dùng toàn JDK chuẩn để chạy ngay.

### Kiểm tra compile-time như thế nào?

Những đoạn **cố ý sai** trong phần giới hạn compile-time không đặt chung với các file demo hợp lệ. Nếu muốn khảo sát, tạo file riêng để xem compiler error; không coi lỗi compiler này là lỗi của bài. Các class trong mục chạy độc lập **không chứa các đoạn sai**.

## 17. Luyện tập nâng cao

### Bài 1 — Đổi cặp check + cast

Đầu vào:

~~~java
Object input = "abc";
if (input instanceof String) {
    String s = (String) input;
    System.out.println(s.length());
}
~~~

**Đáp án:**

~~~java
Object input = "abc";
if (input instanceof String s) {
    System.out.println(s.length());
}
~~~

Cả hai in `3`. Pattern variable `s` chỉ tồn tại khi match.

### Bài 2 — Guard clause

Có phương thức trả `-1` nếu input không phải `String`, ngược lại trả độ dài. Hãy dùng negated pattern.

**Đáp án:**

~~~java
static int length(Object input) {
    if (!(input instanceof String s)) {
        return -1;
    }
    return s.length();
}
~~~

### Bài 3 — Vì sao `||` bên dưới lỗi?

~~~java
if (input instanceof String s || s.length() > 3) {
    use(s);
}
~~~

**Đáp án:** RHS được đánh giá khi pattern ở LHS **false**; biến `s` không được gán. Sửa bằng `&&` nếu ý định là “String và dài hơn 3”, hoặc guard phủ định/nhánh logic khác nếu policy khác.

### Bài 4 — Tình huống `||` hợp lệ

~~~java
if (!(input instanceof String s) || s.isBlank()) {
    return "invalid";
}
return s.strip();
~~~

**Đáp án:** RHS chỉ chạy khi phủ định `!(input instanceof String s)` false, tức pattern match đã true. Sau nhánh `return`, đường tiếp tục cũng được bảo đảm match.

### Bài 5 — Null

`Object input = null;`, điều gì xảy ra với `input instanceof String s`?

**Đáp án:** `false`, không ném `NullPointerException` và không có `s` được gán. Xử lý null/unsupported cases theo domain.

### Bài 6 — List generic

Vì sao `input instanceof List<String> values` không biên dịch?

**Đáp án:** tham số generic `String` không được xác minh tại runtime do erasure; dùng `List<?> values` rồi validate elements nếu phải bảo đảm là String.

### Bài 7 — Kiểu tĩnh đã là String

~~~java
String text = "hello";
if (text instanceof String s) {
    System.out.println(s);
}
~~~

**Đáp án:** Java 17 báo lỗi compile-time cho type pattern redundant vì kiểu tĩnh của operand đã là subtype của pattern type. Dùng trực tiếp `text`.

### Bài 8 — Một getter có side effect

~~~java
if (nextValue() instanceof String) {
    String s = (String) nextValue();
}
~~~

**Đáp án:** hai lần gọi có thể cho hai giá trị khác; lưu snapshot hoặc dùng `if (nextValue() instanceof String s)` nếu yêu cầu là kiểm tra/xử lý **cùng kết quả một lần gọi**. Ghi nhận nếu sửa đổi số lần gọi là thay đổi hành vi.

### Bài 9 — Equals và inheritance

Tại sao không được mặc định thay mọi `getClass() == other.getClass()` trong `equals` bằng `instanceof`?

**Đáp án:** với class cho phép kế thừa, hai kiểm tra có semantics khác nhau; phép thay có thể làm thay đổi equality và vi phạm tính đối xứng/transitivity. Cần giữ chính sách equality cũ hoặc thiết kế lại có test.

### Bài 10 — Chọn refactor hay redesign

Một adapter có 2 nhánh `instanceof` và cast thừa: pattern matching thích hợp. Một lớp xử lý 40 subtype, mỗi subtype có business operation riêng: cân nhắc polymorphism hoặc pattern switch Java21+ nếu đáp ứng target, không chỉ thay mọi cast bằng pattern variables.

## 18. Lệnh chạy toàn bộ ví dụ độc lập

Bảy chương trình đều chỉ sử dụng API/cú pháp có trong **Java 17**. Mỗi `public class` phải nằm trong file có tên trùng, không chứa các mảnh code cố ý sai.

~~~bash
javac --release 17 PayloadRefactorDemo.java
java PayloadRefactorDemo

javac --release 17 GuardScopeDemo.java
java GuardScopeDemo

javac --release 17 BooleanScopeDemo.java
java BooleanScopeDemo

javac --release 17 SingleEvaluationDemo.java
java SingleEvaluationDemo

javac --release 17 GenericItemsDemo.java
java GenericItemsDemo

javac --release 17 TokenEqualsDemo.java
java TokenEqualsDemo

javac --release 17 EventRouterDemo.java
java EventRouterDemo
~~~

Có thể dùng JDK hiện đại hơn, miễn compiler hỗ trợ `--release 17` và môi trường chứa Java SE APIs chuẩn. Không cần `--enable-preview`. Bất kỳ chênh lệch output nào so với bảng trong bài là dấu hiệu cần kiểm tra lại input hoặc source đã sửa; các chương trình không phụ thuộc timing, random, locale mặc định hoặc network.

### Checklist output

| File | Kết quả cần thấy |
| --- | --- |
| `PayloadRefactorDemo` | 5 dòng, tất cả `same=true`. |
| `GuardScopeDemo` | `text:HI`, `blank`, `not-text`, `not-text`. |
| `BooleanScopeDemo` | Xác minh điều kiện phủ định `||` và `&&` với String/Integer. |
| `SingleEvaluationDemo` | `matched=first`, `reads=1`. |
| `GenericItemsDemo` | `[A, B]`, `[]`, `not-list`. |
| `TokenEqualsDemo` | Equality/hashing đúng cho final class. |
| `EventRouterDemo` | `text:hello`, `count:4`, `none`. |

## 19. Checklist code review cho một pull request refactor

- [ ] Cặp `instanceof` và cast cũ kiểm tra **cùng target value**?
- [ ] Type pattern đã được đặt đúng trong điều kiện?
- [ ] Tên pattern variable rõ nghĩa và không xung đột scope?
- [ ] Nếu ghép điều kiện, có dùng `&&` đúng short-circuit?
- [ ] Có hiểu dạng `!(... instanceof ... ) || ...` nếu dùng?
- [ ] Mọi lần sử dụng pattern variable đều ở scope compiler đảm bảo match?
- [ ] Có bảo toàn thứ tự kiểm tra các kiểu chồng lấn (subtype/interfaces)?
- [ ] Có bảo toàn case `null`, type mismatch, blank/invalid domain values?
- [ ] Không đổi `if` thành `else if` hoặc dời `return` một cách vô tình?
- [ ] Biểu thức có side effect chỉ bị đánh giá theo số lần mong muốn?
- [ ] Không dùng `instanceof List<String>` do type erasure?
- [ ] Không thêm pattern check redundant với kiểu tĩnh đã biết?
- [ ] Không nhầm type pattern `instanceof` với record pattern hoặc switch patterns Java21+?
- [ ] Nếu có `equals`, có giữ contract với `hashCode` và inheritance?
- [ ] Mỗi demo/test được biên dịch với `javac --release 17` và không có preview flags?
- [ ] Kiểm thử trước/sau đã có `null`, kiểu không match, collection rỗng, nested cases?
- [ ] Nếu thay đổi logic ngoài việc bỏ cast, đã tách thành commit/test riêng và ghi rõ?
- [ ] Có lý do kiến trúc cho việc giữ type-dispatch thay vì polymorphism nếu nhiều subtype?

## 20. Tài liệu chính thức còn áp dụng

1. [Oracle Java SE 25 — Pattern Matching with `instanceof`](https://docs.oracle.com/en/java/javase/25/language/pattern-matching-instanceof.html): cú pháp, flow scoping, guard clauses, `&&` và trường hợp `||` không hợp lệ.
2. [Oracle Java SE 17 — Pattern Matching for `instanceof`](https://docs.oracle.com/en/java/javase/17/language/pattern-matching-instanceof.html): hướng dẫn trên target JDK17, không dùng preview.
3. [OpenJDK JEP 394 — Pattern Matching for `instanceof`](https://openjdk.org/jeps/394): tính năng chính thức ở Java 16, quy tắc compile-time redundant pattern và pattern variable không còn mặc nhiên `final`.
4. [OpenJDK JEP 305 — Pattern Matching for `instanceof` (Preview)](https://openjdk.org/jeps/305): **chỉ là bối cảnh lịch sử** Java 14; không dùng preview làm cách viết mới.
5. [Oracle Java SE 25 — Java Language Changes by Release](https://docs.oracle.com/en/java/javase/25/language/java-language-changes-release.html): xác nhận mốc preview 14/15 và final ở Java 16.
6. [JLS Java SE 25 — `6.3 Scope of a Declaration`](https://docs.oracle.com/javase/specs/jls/se25/html/jls-6.html#jls-6.3): flow scoping/definitely matched, `&&`, `||`, phủ định và guard clauses.
7. [JLS Java SE 25 — `15.20.2 The `instanceof` Operator`](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.20.2): type comparison vs pattern match, behavior với null và compile-time applicability.
8. [OpenJDK JEP 440 — Record Patterns](https://openjdk.org/jeps/440) và [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): những tính năng Java 21 **khác** type patterns của `instanceof`, chỉ xem khi cần redesign.
9. [Oracle JDK 17 — `List`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html) và [`Objects`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html): API chuẩn dùng trong các ví dụ collection/equality.

**Ghi nhớ:** refactor `instanceof` là cách loại bỏ **cast thừa có kiểm tra**, đồng thời để compiler quản lý scope của biến chỉ khi match thành công. Tính năng đã chính thức từ Java 16; trên Java 17+ không cần preview. Thành công của bài thực hành không nằm ở số dòng code rút ngắn, mà ở việc **giữ đúng kết quả, xử lý `null`/type mismatch, không làm sai short-circuit hoặc số lần đánh giá**, và có test chứng minh hành vi trước/sau nhất quán.