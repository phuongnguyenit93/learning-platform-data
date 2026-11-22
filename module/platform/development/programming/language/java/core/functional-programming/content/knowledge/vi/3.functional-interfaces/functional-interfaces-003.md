# Phương thức `default`, `static` và `private` không làm tăng số phương thức trừu tượng

## 1. Vấn đề cần hiểu

Một **functional interface** trong Java là interface có **đúng một phương thức trừu tượng** theo quy tắc xác định *single abstract method* (SAM). Nó có thể là kiểu đích của biểu thức lambda và method reference. Khi đọc một interface có nhiều khai báo phương thức, không được đếm máy móc số dòng khai báo: phải phân biệt **phương thức trừu tượng** với phương thức đã có phần thân.

Ba nhóm thường gây nhầm:

- **`default`:** phương thức instance đã có phần thân, cung cấp hành vi mặc định cho đối tượng triển khai interface.
- **`static`:** phương thức gắn với chính interface, có phần thân; gọi qua tên interface, thường dùng làm factory hoặc tiện ích.
- **`private` / `private static`:** phương thức hỗ trợ nội bộ có phần thân, chỉ được gọi trong cùng interface; hỗ trợ tái sử dụng logic mà không công khai API.

**Cả ba nhóm trên đều không tạo thêm phương thức trừu tượng.** Một interface có một SAM cộng với nhiều phương thức `default`, `static` và `private` vẫn có thể được đánh dấu `@FunctionalInterface`. Điểm cần nhớ: *không làm tăng số SAM* không có nghĩa là các phương thức này không tồn tại, không có hành vi, hoặc có thể gọi giống nhau.

Tính năng `default` và `static` trong interface có từ Java 8; `private` instance và `private static` có từ Java 9. Ví dụ trong bài sử dụng **Java 17 trở lên**.

## 2. Phương thức nào được tính là trừu tượng?

Một khai báo instance không có phần thân, chẳng hạn `boolean test(String value);`, là phương thức trừu tượng cần được lớp triển khai cung cấp (trừ khi lớp đó vẫn trừu tượng). Với interface thông thường, phương thức instance không có modifier phù hợp được hiểu là `public abstract`.

~~~java
@FunctionalInterface
interface Check {
    boolean test(String value); // SAM duy nhất
}
~~~

`Check` có thể được triển khai bằng lambda vì chỉ có một hợp đồng trừu tượng:

~~~java
Check hasContent = value -> value != null && !value.isBlank();
boolean ok = hasContent.test("Java"); // true
~~~

Hai khối trên là **mã minh họa đặt cùng phạm vi có thể truy cập `Check`**; chương trình Java độc lập đầy đủ nằm ở phần 5.

### Cách đếm chính xác hơn

Không phải bất cứ khai báo nào có dấu `;` cũng là một SAM riêng:

1. Bỏ qua các phương thức có phần thân: `default`, `static` và `private` không phải các phương thức trừu tượng.
2. Những khai báo có chữ ký tương ứng với phương thức `public` của `java.lang.Object` (như `equals(Object)`, `hashCode()`, `toString()`) **không được tính** khi xác định SAM của functional interface.
3. Với các interface kế thừa, phải xét những phương thức trừu tượng *thực sự còn lại* và quan hệ chữ ký/override tương đương của chúng, không chỉ cộng số khai báo từ từng interface cha.
4. `@FunctionalInterface` không tự biến một interface thành functional; nó nhờ compiler kiểm tra quy tắc và báo lỗi khi không thỏa. Có thể bỏ annotation mà interface vẫn functional nếu đủ điều kiện.

Ví dụ có thêm khai báo `equals` vẫn hợp lệ vì `equals(Object)` là phương thức công khai của `Object`:

~~~java
@FunctionalInterface
interface Describer {
    String describe(String value);
    boolean equals(Object other); // Không tạo SAM thứ hai
}
~~~

Không được suy rộng quy tắc này cho bất kỳ phương thức nào "trông giống" API Object: chữ ký và ngữ nghĩa override phải đúng. Mặt khác, không được khai báo `default String toString()` hay `default boolean equals(Object)` để ghi đè một phương thức của `Object` trong interface; Java cấm default method override các phương thức không phải `final` của `Object` theo quy tắc ngôn ngữ.

## 3. So sánh bốn loại phương thức trong interface

| Loại | Phần thân? | Có tính vào SAM? | Cách gọi/đối tượng sử dụng | Công dụng chính |
| --- | --- | --- | --- | --- |
| `abstract` | Không | **Có**, với các ngoại lệ SAM theo ngôn ngữ | Gọi trên đối tượng triển khai; lambda cung cấp hiện thực | Định nghĩa hợp đồng bắt buộc |
| `default` | Có | **Không** | Gọi trên đối tượng triển khai; có thể override | Thêm hành vi mặc định, phối hợp các phương thức instance |
| `static` | Có | **Không** | `TênInterface.phươngThức(...)` | Factory, tiện ích gắn với hợp đồng |
| `private` | Có | **Không** | Chỉ các phương thức bên trong cùng interface | Dùng chung logic instance, có thể gọi SAM trên `this` |
| `private static` | Có | **Không** | Chỉ các phương thức bên trong cùng interface | Logic tiện ích nội bộ không cần trạng thái instance |

Lưu ý: từ khóa `abstract` không nhất thiết phải ghi tường minh trong khai báo `public` instance của interface. Không thể kết hợp `abstract` với `default`, `static` hay `private` để tạo "phương thức vừa có thân vừa trừu tượng".

### 3.1. `default`: hành vi có sẵn cho instance

~~~java
@FunctionalInterface
interface Validator {
    boolean valid(String text);

    default boolean validTrimmed(String text) {
        return valid(text == null ? "" : text.trim());
    }
}
~~~

Phương thức `valid(String)` là SAM. `validTrimmed(String)` **đã có thân** nên không thêm hợp đồng trừu tượng; nó gọi lại SAM thông qua `valid(...)`. Một lambda `Validator validator = s -> !s.isEmpty();` đủ để thực hiện cả hai hành vi. Lớp triển khai cũng có thể override `validTrimmed` nếu muốn.

Trường hợp thực tế: bổ sung một thao tác tiện ích dựa trên phép kiểm tra cốt lõi mà không bắt buộc tất cả implementation viết lại cùng một logic.

### 3.2. `static`: factory hoặc thuật toán dùng chung

~~~java
@FunctionalInterface
interface IntRule {
    boolean test(int number);

    static IntRule greaterThan(int boundary) {
        return value -> value > boundary;
    }
}
~~~

`IntRule.greaterThan(10)` tạo ra một `IntRule`. Phương thức `greaterThan` có phần thân và trả về lambda, không phải SAM bổ sung. **Static method của interface không được kế thừa thành static method của lớp triển khai hoặc subinterface.** Vì vậy hãy gọi `IntRule.greaterThan(10)` thay vì `SomeImplementation.greaterThan(10)`.

Một phương thức `static` không dùng `this`; nó không phải phương thức instance có thể được override. Để tạo một bản kiểm tra phụ thuộc dữ liệu của đối tượng, hãy dùng SAM hoặc instance/default method phù hợp.

### 3.3. `private`: chia sẻ triển khai nội bộ

~~~java
@FunctionalInterface
interface NormalizedRule {
    boolean test(String value);

    default boolean check(String value) {
        return test(normalize(value));
    }

    default String display(String value) {
        return check(value) ? "OK" : "NO";
    }

    private static String normalize(String value) {
        return value == null ? "" : value.trim();
    }
}
~~~

`normalize` chỉ là helper bên trong `NormalizedRule`, không thể được gọi từ ngoài hoặc bị lớp triển khai override. Nếu helper cần gọi trực tiếp SAM hay các instance method khác, có thể dùng `private` instance method:

~~~java
private boolean evaluate(String normalizedValue) {
    return test(normalizedValue);
}
~~~

Đoạn `evaluate` trên là **mảnh mã đặt bên trong interface có phương thức `test(String)`**, không phải chương trình độc lập. Private instance method có thể dùng hành vi instance; private static method chỉ nên dùng dữ liệu truyền vào hoặc thành phần static. Đừng cố khai báo `private abstract`: đó là tổ hợp modifier không hợp lệ.

Private method giúp tránh lặp logic ở nhiều default method, đồng thời giữ bề mặt API nhỏ. Đây là điểm khác biệt quan trọng với việc tạo thêm default method chỉ để chia sẻ một hàm hỗ trợ vốn không nên công khai.

## 4. Vì sao nhiều phương thức nhưng vẫn dùng được lambda?

Lambda không hiện thực tất cả những phương thức nhìn thấy trong interface: nó cung cấp hiện thực cho **một hợp đồng trừu tượng duy nhất**. Các hành vi `default` đã có phần thân, các `static` thuộc interface và các `private` chỉ phục vụ triển khai bên trong.

Ví dụ, nếu interface có cấu trúc:

~~~text
TextRule
├─ test(String)                 // public abstract → 1 SAM
├─ testNormalized(String)       // default → 0 SAM
├─ explain(String)              // default → 0 SAM
├─ minLength(int)               // static → 0 SAM
├─ evaluate(String)             // private instance → 0 SAM
└─ normalize(String)            // private static → 0 SAM
Tổng số phương thức trừu tượng cần triển khai: 1
~~~

Một biểu thức `value -> value != null && value.length() >= 3` đủ làm hiện thực `test`. Sau đó có thể gọi `testNormalized` hoặc `explain` trên đối tượng hàm vừa tạo.

Chính cơ chế này làm cho một functional interface có thể cung cấp API giàu tiện ích hơn mà vẫn duy trì tính tương thích với lambda.

## 5. Ví dụ Java 17 hoàn chỉnh: SAM cùng default, static và private

Tạo tệp **`FunctionalInterfaceMethodsDemo.java`** với nội dung sau:

~~~java
public class FunctionalInterfaceMethodsDemo {

    @FunctionalInterface
    interface TextRule {
        // Phương thức trừu tượng duy nhất (SAM).
        boolean test(String value);

        // Default #1: cung cấp hành vi trên đối tượng.
        default boolean testNormalized(String value) {
            return evaluate(normalize(value));
        }

        // Default #2: tái sử dụng một default method khác.
        default String explain(String value) {
            return testNormalized(value) ? "PASS" : "FAIL";
        }

        // Private instance: gọi hợp đồng instance test(...).
        private boolean evaluate(String value) {
            return test(value);
        }

        // Private static: helper thuần dựa trên tham số truyền vào.
        private static String normalize(String value) {
            return value == null ? "" : value.trim();
        }

        // Static factory: tạo một cách triển khai SAM.
        static TextRule minLength(int minimum) {
            if (minimum < 0) {
                throw new IllegalArgumentException("minimum < 0");
            }
            return value -> value != null && value.length() >= minimum;
        }
    }

    public static void main(String[] args) {
        TextRule atLeast3 = TextRule.minLength(3);
        TextRule onlyLetters = value ->
                value != null
                && !value.isEmpty()
                && value.codePoints().allMatch(Character::isLetter);

        System.out.println(atLeast3.explain("  Java  "));
        System.out.println(atLeast3.explain("  Go  "));
        System.out.println(onlyLetters.testNormalized("  Java "));
        System.out.println(TextRule.minLength(3).test("Go"));
    }
}
~~~

Biên dịch và chạy bằng JDK 17+:

~~~bash
javac -encoding UTF-8 FunctionalInterfaceMethodsDemo.java
java FunctionalInterfaceMethodsDemo
~~~

**Kết quả chính xác:**

~~~text
PASS
FAIL
true
false
~~~

Giải thích từng dòng:

1. `"  Java  "` được `normalize` thành `"Java"` (4 ký tự), đáp ứng độ dài tối thiểu 3 → `PASS`.
2. `"  Go  "` được chuẩn hóa thành `"Go"` (2 ký tự), không đủ độ dài 3 → `FAIL`.
3. Lambda `onlyLetters` kiểm tra điểm mã Unicode bằng `codePoints()`, nên `"Java"` chỉ gồm chữ cái → `true`. Dùng `codePoints` thay vì `chars` là hữu ích khi cần xét các ký tự Unicode ngoài BMP.
4. Gọi trực tiếp `test("Go")` không chuẩn hóa, nhưng chiều dài vẫn chỉ 2 nên → `false`.

Compiler chấp nhận `@FunctionalInterface` vì phương thức trừu tượng duy nhất là `test(String)`. Trong chương trình vừa dùng lambda để triển khai SAM, vừa gọi factory `static` và các phương thức `default`, trong khi helper `private` được gọi kín bên trong interface. Các phương thức có thân không khiến interface mất tính functional.

## 6. Trường hợp kế thừa và xung đột cần biết

### 6.1. Kế thừa default method không thêm SAM

~~~java
interface HasLabel {
    default String label() {
        return "ready";
    }
}

@FunctionalInterface
interface LabeledTask extends HasLabel {
    void runTask();
}
~~~

`LabeledTask` vẫn chỉ có một phương thức trừu tượng `runTask()`. Một lớp triển khai có thể dùng `label()` đã được kế thừa hoặc override nó. Trái lại, `static` của `HasLabel` (nếu có) không được kế thừa như phương thức thành viên của `LabeledTask`.

### 6.2. Hai default method trùng chữ ký có thể xung đột

~~~java
interface First {
    default String name() { return "first"; }
}

interface Second {
    default String name() { return "second"; }
}

class Combined implements First, Second {
    @Override
    public String name() {
        return First.super.name() + "+" + Second.super.name();
    }
}
~~~

Vì hai interface độc lập cung cấp hai phiên bản `name()` mặc định, `Combined` phải giải quyết xung đột bằng cách override. Trong ví dụ, lời gọi `First.super.name()` và `Second.super.name()` chọn rõ bản mặc định muốn dùng. **Xung đột default method là vấn đề phân giải hành vi kế thừa**, không tự làm tăng số phương thức trừu tượng trong từng interface nguồn.

Ngoài ra, phương thức instance cụ thể được kế thừa từ class có thể được ưu tiên hơn default method cùng chữ ký từ interface theo quy tắc phân giải của Java.

### 6.3. Interface con có thể biến default method thành abstract

Điều cần phân biệt: **việc có một default method không làm tăng SAM**, nhưng interface con *có thể tái khai báo phương thức đó thành trừu tượng*; khi ấy phương thức trong interface con phải được tính lại như một hợp đồng cần triển khai.

~~~java
interface Parent {
    default void reset() {}
}

interface Child extends Parent {
    void reset();   // Tái trừu tượng hóa hành vi được kế thừa
    void process(); // Một phương thức trừu tượng khác
}
~~~

`Child` ở đây có hai hợp đồng trừu tượng (`reset` và `process`), vì vậy **không phải functional interface**. Nếu thêm `@FunctionalInterface` lên `Child`, trình biên dịch báo lỗi. Không được kết luận "hễ nguồn gốc là default thì mãi mãi không bị tính".

### 6.4. Chữ ký tương đương và Object

Nếu hai interface cha khai báo cùng một abstract method có chữ ký override tương đương, số SAM hiệu lực có thể vẫn là **một** sau khi kết hợp. Ngược lại, hai phương thức trừu tượng độc lập với các chữ ký khác nhau làm interface không còn functional. Các chữ ký tương đương cần xét kiểu trả về hợp lệ và quy tắc override của Java, không suy đoán chỉ từ tên phương thức.

Các phương thức `public` của `Object` như `equals(Object)` vẫn theo ngoại lệ đã nêu ở phần 2; không được coi là một SAM bổ sung chỉ vì chúng được khai báo lại trong interface.

## 7. Các lỗi biên dịch và nhầm lẫn thường gặp

| Nhầm lẫn | Kết quả hoặc nguyên nhân | Cách sửa |
| --- | --- | --- |
| Đếm mọi dòng khai báo method là SAM | Interface có default/static/private bị đánh giá nhầm là không functional | Chỉ xét các hợp đồng trừu tượng còn hiệu lực |
| Cho rằng `static` phải có một class triển khai | Static method có thân thuộc về interface | Gọi qua `TênInterface.method()` |
| Gọi `Impl.minLength(...)` thay `TextRule.minLength(...)` | Static method của interface không kế thừa qua class triển khai | Dùng tên interface khai báo phương thức |
| Gọi một `private` method từ code ngoài interface | Không truy cập được do mức độ hiển thị | Dùng public/default API phù hợp |
| Viết `private abstract void help();` | Private abstract method không hợp lệ | Chọn abstract SAM công khai hoặc private method có thân |
| Viết `default void f();` | Default method bắt buộc có thân | Viết thân hoặc khai báo abstract |
| Khai báo hai abstract methods độc lập và gắn `@FunctionalInterface` | Compiler báo interface không hợp lệ với annotation | Thiết kế lại hợp đồng thành một SAM, tách interface nếu cần |
| Hai interface cha có default method trùng chữ ký | Lớp triển khai bị xung đột phương thức kế thừa | Override và chọn hành vi cụ thể |
| Nghĩ `@FunctionalInterface` bắt buộc để dùng lambda | Annotation chỉ là kiểm tra lúc biên dịch | Có thể dùng lambda khi interface thỏa quy tắc SAM |
| Cố khai báo default method override `equals`/`toString` của `Object` | Java không cho default method override như vậy | Để implementation xử lý hoặc dùng tên API khác |

### Ví dụ lỗi cố ý để tự nhận diện

Khối dưới đây **không biên dịch được** vì có hai phương thức trừu tượng độc lập; nó chỉ dùng để phân tích lỗi:

~~~java
@FunctionalInterface
interface InvalidRule {
    boolean test(String value);
    int score(String value); // SAM thứ hai: không hợp lệ

    default String label() {
        return "invalid";
    }

    static InvalidRule example() {
        throw new UnsupportedOperationException();
    }
}
~~~

`label` và `example` không làm tăng SAM. Hai phương thức `test` và `score` mới là nguyên nhân. Để sửa, cần xác định nhiệm vụ chính của interface: chẳng hạn chỉ để `test` là abstract, còn tính `score` dựa trên `test` bằng một default method *nếu điều đó đúng ngữ nghĩa*, hoặc chia các trách nhiệm thành hai interface. Không nên gộp chức năng tùy tiện chỉ để annotation qua được compiler.

## 8. Quy trình kiểm tra một interface có functional hay không

Khi gặp một interface mới hoặc chỉnh sửa API có sẵn, thực hiện:

1. **Đọc phương thức trừu tượng:** các method instance không có thân trong interface và các abstract methods kế thừa còn hiệu lực.
2. **Loại các method không phải abstract:** `default`, `static`, `private`/`private static`; xem cả inherited default methods.
3. **Xét ngoại lệ Object và chữ ký override tương đương:** không cộng trùng những hợp đồng được Java gộp, không tính các khai báo tương ứng phương thức public của `Object`.
4. **Kiểm tra kế thừa:** có tái trừu tượng hóa default method, hai abstract khác nhau hoặc xung đột default chưa xử lý không?
5. **Thêm `@FunctionalInterface` nếu chủ đích là API SAM:** để compiler bảo vệ ràng buộc khi mã phát triển.
6. **Thử gán lambda hoặc method reference:** lambda phải phù hợp số tham số, kiểu tham số và giá trị trả về của SAM; checked exceptions cũng phải tương thích hợp đồng SAM.

Nếu kết quả là đúng một abstract method hợp lệ, interface có thể là kiểu đích của lambda. Một lambda thực chất chỉ mô tả cách thực hiện SAM; default methods cung cấp hành vi tái sử dụng và các static/private methods tổ chức API cùng triển khai.

## 9. Bài tập tự kiểm tra

**Bài 1 — Đếm SAM.** Xét:

~~~java
@FunctionalInterface
interface Formatter {
    String format(String input);

    default String formatOrEmpty(String input) {
        return input == null ? "" : format(input);
    }

    static Formatter identity() {
        return value -> value;
    }

    private static boolean missing(String input) {
        return input == null;
    }
}
~~~

Có bao nhiêu phương thức trừu tượng? **Một: `format`.** Các phương thức còn lại có thân. Chú ý `missing` chưa được gọi vẫn là một private static method hợp lệ (compiler có thể có cảnh báo tùy công cụ, nhưng không làm thay đổi SAM).

**Bài 2 — Viết lambda.** Tạo `Formatter formatter = s -> s.trim().toUpperCase();`, thử `formatter.formatOrEmpty(" java ")` và trường hợp `null`. Kết quả tương ứng `"JAVA"` và `""`; thao tác mặc định tránh chuyển `null` vào lambda.

**Bài 3 — Thêm một default method.** Thêm phương thức `default int lengthOf(String input) { return formatOrEmpty(input).length(); }` vào `Formatter`. Giải thích vì sao lambda ban đầu vẫn hợp lệ: phương thức mới có phần thân nên không phát sinh hợp đồng trừu tượng thứ hai.

**Bài 4 — Tìm lỗi.** Đổi `private static boolean missing(...)` thành `private abstract boolean missing(...);`. Dự đoán lỗi biên dịch và nêu quy tắc modifier liên quan. Sau đó thử thêm `int size(String value);` để thấy tác dụng của `@FunctionalInterface` khi thật sự xuất hiện SAM thứ hai.

**Bài 5 — Kế thừa.** Tạo hai interface có cùng default method và một class implements cả hai. Tự viết override để xử lý xung đột; phân biệt vấn đề kế thừa default với việc đếm SAM.

## 10. Ghi nhớ

- Functional interface có **một hợp đồng trừu tượng duy nhất** theo luật SAM, dù có thể công khai nhiều phương thức khác.
- `default` (Java 8+) có thân, có thể được class triển khai override; `static` (Java 8+) có thân, gọi qua tên interface và không được kế thừa như instance API.
- `private`/`private static` (Java 9+) có thân và chỉ hỗ trợ triển khai trong chính interface.
- Không cộng các method trên vào số SAM. Cần xét thêm ngoại lệ `Object`, chữ ký tương đương, kế thừa và việc một default method có bị tái khai báo abstract ở interface con hay không.
- `@FunctionalInterface` là công cụ bảo vệ quy tắc tại thời điểm biên dịch. Khi cần duy trì API phù hợp lambda, ưu tiên thêm hành vi hợp lý bằng default/static/private thay vì vô tình thêm abstract method thứ hai.

**Tài liệu tra cứu chính thức:** Javadoc `java.lang.FunctionalInterface`, Java Language Specification mục *Functional Interfaces* (JLS `9.8) và *Interface Method Declarations* (JLS `9.4), cùng Javadoc `java.util.function`.
