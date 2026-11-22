# Annotation trên PARAMETER và LOCAL_VARIABLE trong Java

## 1. Hai đích áp dụng khác nhau

Java cho phép giới hạn vị trí một annotation được sử dụng thông qua meta-annotation `@Target`. Khi khai báo `@Target(ElementType.PARAMETER)` hoặc `@Target(ElementType.LOCAL_VARIABLE)`, chúng ta đang mô tả **hai loại khai báo khác nhau**:

- **`ElementType.PARAMETER`**: annotation được áp dụng lên **khai báo tham số hình thức** của phương thức hoặc constructor. Ví dụ: tham số `name` trong `void greet(@Input String name)`.
- **`ElementType.LOCAL_VARIABLE`**: annotation được áp dụng lên **khai báo biến cục bộ** bên trong khối mã, ví dụ: biến `message` trong phần thân phương thức `@LocalInfo String message = "...";`.

Cả hai đều là metadata gắn với một khai báo ở mã Java. Chúng **không tự thay đổi dữ liệu tham số hay biến, không tự validate, không cấp quyền và không sinh logic kiểm tra**. Muốn tạo hành vi cần có công cụ, annotation processor hoặc mã của ứng dụng xử lý thông tin tương ứng.

Hai đích này đặc biệt dễ bị nhầm vì tham số phương thức và biến cục bộ đều có tên và kiểu dữ liệu, thường cùng xuất hiện trong một phương thức. Tuy nhiên, chúng có **vị trí khai báo, phạm vi tồn tại và khả năng quan sát qua reflection khác nhau**.

## 2. Khai báo annotation với @Target

Để định nghĩa loại annotation chỉ gắn lên tham số:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.PARAMETER)
@interface Input {
    String value();
}
```

Để định nghĩa loại chỉ gắn lên biến cục bộ:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.LOCAL_VARIABLE)
@interface LocalInfo {
    String value();
}
```

Hai ví dụ trên là **hai đoạn khai báo độc lập để giải thích `@Target`**. Khi gom vào một file thực tế, chỉ import các class một lần.

Có thể cho phép **cả hai vị trí** bằng mảng `ElementType`:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target({ElementType.PARAMETER, ElementType.LOCAL_VARIABLE})
@interface Track {
    String value();
}
```

Lúc này `@Track` được phép đặt trên tham số hình thức và biến cục bộ, nhưng **không tự động được phép đặt trên class, field hoặc phương thức**. Compiler kiểm tra `@Target` tại nơi sử dụng.

### So sánh nhanh

| Tiêu chí | `PARAMETER` | `LOCAL_VARIABLE` |
| --- | --- | --- |
| Nơi gắn | Khai báo tham số hình thức của method/constructor | Khai báo biến cục bộ trong khối mã |
| Ví dụ | `void pay(@Input String account)` | `@LocalInfo String receipt = "...";` |
| Phần tử mà annotation mô tả | Tham số `account` | Biến cục bộ `receipt` |
| Kiểm tra đích ở compile time | Có | Có |
| Có thể đọc bằng Java Core reflection? | Có thể, với annotation có `RUNTIME` retention, qua `Parameter` | Không có API reflection Java Core tương đương cho annotation khai báo biến cục bộ |
| Có tự tạo hành vi? | Không | Không |

`PARAMETER` cũng được dùng trong bối cảnh **constructor parameter**, không riêng method parameter. Một biến `String account` khai báo bên trong phần thân phương thức là biến cục bộ, dù giá trị của nó đến từ một tham số.

## 3. Annotation trên tham số: PARAMETER

Xét phương thức:

```java
void register(
        @Input("username") String username,
        @Input("age") int age) {
    // ...
}
```

Hai `@Input` ở đây cùng loại nhưng được đặt trên **hai khai báo tham số khác nhau**. Đây không phải trường hợp lặp annotation trên cùng một khai báo, nên **không cần `@Repeatable`**.

Tác dụng của chúng phụ thuộc một thành phần biết đọc `@Input`: ví dụ một trình ánh xạ tham số tự viết có thể đọc chuỗi `"username"` và `"age"` để ghép dữ liệu từ yêu cầu đầu vào. Java Core không tự sinh cơ chế ánh xạ đó.

### 3.1. Đọc annotation tham số bằng reflection

Khi annotation có `@Retention(RetentionPolicy.RUNTIME)`, chương trình có thể truy xuất annotation trên tham số thông qua `java.lang.reflect.Parameter`.

Luồng phổ biến:

1. Lấy `Method` hoặc `Constructor` từ reflection.
2. Gọi `getParameters()` để lấy các `Parameter`.
3. Dùng `parameter.getAnnotation(Input.class)` hoặc `parameter.isAnnotationPresent(Input.class)`.
4. Đọc phần tử bên trong annotation nếu tìm thấy.

`Method.getParameterAnnotations()` cũng trả về mảng annotation theo từng tham số. `Parameter.getAnnotations()` cung cấp API thao tác trực tiếp trên một tham số.

**Lưu ý:** Java có thể không lưu tên tham số nguồn (`username`, `age`) theo cách mà `Parameter.getName()` hiển thị khi biên dịch thông thường. Tùy compiler và cờ `-parameters`, tên quan sát được có thể là `arg0`, `arg1`. Điều này **độc lập với việc annotation `@Input("username")` có được lưu giữ ở runtime hay không**. Phần tử `value()` của annotation giữ chuỗi do lập trình viên đặt.

### 3.2. Constructor parameter

```java
class Account {
    private final String id;

    Account(@Input("accountId") String id) {
        this.id = id;
    }
}
```

`@Input` gắn vào khai báo tham số `id` của constructor và hợp lệ với `ElementType.PARAMETER`. Nếu có `RUNTIME` retention, reflection qua `Constructor.getParameters()` có thể đọc nó tương tự method parameter.

Không nên nhầm tham số constructor với field `id`: hai vị trí là hai phần tử chương trình khác nhau. Muốn gắn annotation trực tiếp vào field cần target phù hợp như `ElementType.FIELD`.

## 4. Annotation trên biến cục bộ: LOCAL_VARIABLE

Xét đoạn mã bên trong phương thức:

```java
void process(String input) {
    @LocalInfo("normalized value")
    String normalized = input.trim();

    @LocalInfo("result counter")
    int count = normalized.length();

    System.out.println(count);
}
```

`normalized` và `count` là **biến cục bộ**; `@LocalInfo` dùng `ElementType.LOCAL_VARIABLE` nên hợp lệ tại những khai báo này.

Đừng hiểu annotation như một lời gọi hàm: `@LocalInfo` không khiến `trim()` chạy thêm, không chèn log, không kiểm soát phép gán và cũng không tự thay đổi thời gian sống của biến.

### 4.1. Thời điểm và phạm vi của biến cục bộ

Biến cục bộ được khai báo bên trong khối, không phải thành viên của class và không phải tham số của method. Phạm vi sử dụng của tên biến phụ thuộc cấu trúc khối, quy tắc definite assignment và ngữ nghĩa Java.

Ví dụ:

```java
void calculate(int amount) {
    @LocalInfo("local copy")
    int doubled = amount * 2;
    System.out.println(doubled);
}
```

`amount` là **PARAMETER**, còn `doubled` là **LOCAL_VARIABLE**. Việc chúng cùng có kiểu `int` không làm chúng cùng loại khai báo.

### 4.2. Có đọc được LOCAL_VARIABLE bằng reflection không?

Đây là khác biệt quan trọng nhất khi ứng dụng thực tế.

`Method`, `Constructor` và `Parameter` là các đối tượng của Java Reflection API, nhưng **Java Core không có đối tượng `LocalVariable` trong reflection để tìm từng biến cục bộ và gọi `getAnnotation` trên khai báo biến ấy**.

Ngay cả khi loại annotation cho `LOCAL_VARIABLE` có `@Retention(RetentionPolicy.RUNTIME)`, điều đó **không đồng nghĩa** ứng dụng có thể dùng reflection thông thường để lấy `@LocalInfo` từ biến `doubled`. Đối với annotation khai báo biến cục bộ, Java không đảm bảo metadata tương ứng được đưa vào class file theo cách API reflection dành cho tham số hoạt động.

Nếu bài toán là phân tích, xác thực hoặc biến đổi thông tin ở cấp biến cục bộ, cần xem xét công cụ ở thời điểm biên dịch (ví dụ annotation processor có giới hạn khả năng quan sát, compiler plugin hoặc công cụ phân tích mã nguồn) thay vì giả định có thể dùng `Method.getParameters()` để thấy biến cục bộ. Một số annotation gắn vào **kiểu được sử dụng** của biến có quy tắc lưu metadata khác; đó là `TYPE_USE`, được phân biệt ở mục 7.

### 4.3. Trường hợp `var`

Ở Java 17+, `var` dùng suy luận kiểu cho các biến cục bộ trong ngữ cảnh hợp lệ. Khi annotation nhắm vào khai báo biến cục bộ, có thể viết:

```java
void run() {
    @LocalInfo("inferred local")
    var message = "ready";

    System.out.println(message);
}
```

Ở đây `var` là cú pháp suy luận kiểu của Java, không tạo ra một đích annotation riêng. `message` vẫn là biến cục bộ. Hãy dùng `@Target(LOCAL_VARIABLE)` khi mục tiêu là khai báo biến.

## 5. Ví dụ Java 17+ chạy độc lập: quan sát hai đích áp dụng

Ví dụ này định nghĩa annotation cho **chỉ tham số**, **chỉ biến cục bộ** và **cả hai**. Chương trình chỉ sử dụng JDK, không cần thư viện thứ ba.

Tạo file **ParameterLocalTargetDemo.java**:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;
import java.lang.reflect.Parameter;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.PARAMETER)
@interface InputName {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.LOCAL_VARIABLE)
@interface LocalHint {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.PARAMETER, ElementType.LOCAL_VARIABLE})
@interface Track {
    String value();
}

public class ParameterLocalTargetDemo {
    static void greet(
            @InputName("person")
            @Track("received")
            String name) {
        @LocalHint("computed message")
        @Track("temporary")
        String greeting = "Hello, " + name;

        System.out.println(greeting);
    }

    public static void main(String[] args) throws NoSuchMethodException {
        Method method = ParameterLocalTargetDemo.class
                .getDeclaredMethod("greet", String.class);

        Parameter parameter = method.getParameters()[0];
        InputName input = parameter.getAnnotation(InputName.class);

        System.out.println(input.value());
        System.out.println(parameter.isAnnotationPresent(Track.class));

        greet("Lan");
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên, tại thư mục chứa file:

```bash
javac ParameterLocalTargetDemo.java
java ParameterLocalTargetDemo
```

Stdout chính xác:

```text
person
true
Hello, Lan
```

**Giải thích kết quả:**

1. `@InputName("person")` có target `PARAMETER`; vì retention `RUNTIME`, `parameter.getAnnotation(InputName.class)` trả về annotation gắn trên tham số `name`. Do đó in ra `person`.
2. `@Track("received")` cũng được gắn lên tham số `name`, vì `@Track` cho phép `PARAMETER`; `isAnnotationPresent(Track.class)` trả về `true`.
3. Trong `greet`, `@LocalHint("computed message")` và `@Track("temporary")` cùng gắn lên khai báo biến cục bộ `greeting`. Chúng **không xuất hiện trong `parameter.getAnnotations()`**, vì tham số và biến cục bộ là hai khai báo riêng.
4. `greet("Lan")` thực hiện phép nối chuỗi bình thường để tạo `Hello, Lan`. Các annotation không tự can thiệp vào logic của phương thức.

Đặt `@Retention(RUNTIME)` cho `LocalHint` trong ví dụ **không mở ra một API reflection mới để đọc `@LocalHint` trên `greeting`**. Nó giúp minh họa rõ rằng *chính sách retention* và *khả năng truy cập theo loại phần tử thông qua API reflection* là hai vấn đề khác nhau.

## 6. Những vị trí hợp lệ và không hợp lệ

### 6.1. Chỉ cho PARAMETER

```java
@Target(ElementType.PARAMETER)
@interface ParamOnly {}

class Example {
    void f(@ParamOnly String name) {} // Hợp lệ.

    void g() {
        // @ParamOnly String local = "x"; // LỖI nếu bỏ comment.
    }
}
```

Khi `@ParamOnly` chỉ có target `PARAMETER`, đặt nó trước khai báo biến cục bộ là sai.

### 6.2. Chỉ cho LOCAL_VARIABLE

```java
@Target(ElementType.LOCAL_VARIABLE)
@interface LocalOnly {}

class Example {
    // void f(@LocalOnly String name) {} // LỖI nếu bỏ comment.

    void g() {
        @LocalOnly
        String local = "x"; // Hợp lệ.
    }
}
```

Khi `@LocalOnly` chỉ có target `LOCAL_VARIABLE`, đặt nó lên tham số `name` là sai.

Hai đoạn ở mục 6 là **đoạn minh họa độc lập** và cần import `java.lang.annotation.ElementType`, `java.lang.annotation.Target` trước khi biên dịch thành file hoàn chỉnh. Không ghép chúng nguyên trạng vào một file vì cả hai cùng dùng tên lớp `Example`.

### 6.3. Nhiều annotation trên cùng một khai báo

Một annotation được phép target `PARAMETER` có thể đứng cạnh annotation khác cũng cho phép `PARAMETER`:

```java
void send(@InputName("email") @Track("request") String email) {
    // ...
}
```

Không cần một thứ tự đặc biệt cho các annotation khác loại. Sự xuất hiện của nhiều annotation chỉ xác định **metadata nào gắn với tham số**; hành vi và thứ tự thực thi nghiệp vụ phụ thuộc thành phần xử lý.

## 7. Đừng nhầm PARAMETER và LOCAL_VARIABLE với TYPE_USE

Một vấn đề thực tế thường gặp là annotation nằm ngay trước **kiểu** của tham số hoặc biến:

```java
@Marker String name
```

Nhìn vị trí văn bản chưa đủ để biết annotation đang nhắm đến **khai báo tham số/biến** hay **việc sử dụng kiểu `String`**. Java có một target khác:

- `ElementType.TYPE_USE`: nhắm đến **việc sử dụng một kiểu** (type use), ví dụ kiểu trong khai báo biến hoặc tham số, đối số generic, cast, hay những ngữ cảnh type-use hợp lệ khác.
- `ElementType.PARAMETER`: nhắm đến khai báo tham số hình thức.
- `ElementType.LOCAL_VARIABLE`: nhắm đến khai báo biến cục bộ.

Ví dụ minh họa annotation thuộc TYPE_USE:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.TYPE_USE)
@interface ReadOnlyType {}

class Example {
    void print(@ReadOnlyType String text) {
        @ReadOnlyType String local = text;
        System.out.println(local);
    }
}
```

`@ReadOnlyType` trong ví dụ gắn vào **kiểu được sử dụng**. Nó không phải annotation được khai báo với `@Target(PARAMETER)` hoặc `@Target(LOCAL_VARIABLE)`, dù cũng có thể được viết ngay trước `String` ở hai vị trí đó.

**Điểm quan trọng về reflection:** Với method parameter, API `Parameter.getAnnotations()` dùng để đọc annotation *trên khai báo tham số*. Còn thông tin annotation của **kiểu tham số** được biểu diễn qua `Parameter.getAnnotatedType()` và `AnnotatedType` khi metadata được giữ tại runtime và được hỗ trợ. Đừng kỳ vọng hai API luôn trả về cùng tập annotation.

Với biến cục bộ, Java reflection thông thường vẫn không cho phép duyệt các khai báo biến cục bộ như nó duyệt `Method` hoặc `Parameter`. Những công cụ đọc bytecode hoặc compiler APIs phục vụ bài toán khác với reflection truyền thống.

### TYPE_USE không tự đồng nghĩa với validation

Một annotation như `@ReadOnlyType` chỉ trở thành một ràng buộc kiểm tra thực tế nếu có compiler plugin, type checker hoặc công cụ khác hiểu nó. Java không tự biến mọi annotation `TYPE_USE` thành cơ chế bất biến, non-null hay kiểm tra kiểu mở rộng.

## 8. Retention và khả năng quan sát metadata

`@Target` và `@Retention` giải quyết hai câu hỏi độc lập:

- **`@Target`:** annotation được đặt ở đâu trong source?
- **`@Retention`:** metadata của annotation được giữ đến giai đoạn nào?

Các chính sách retention thường gặp:

| Retention | Ý nghĩa | `PARAMETER` qua reflection | `LOCAL_VARIABLE` qua reflection |
| --- | --- | --- | --- |
| `SOURCE` | Chỉ dùng tại source/compile time | Không | Không |
| `CLASS` | Giữ trong class file theo quy tắc retention | Không thông qua API runtime annotation | Không có API tương ứng |
| `RUNTIME` | Cho phép runtime truy cập metadata ở các vị trí được hỗ trợ | Có, bằng `Parameter` khi annotation hiện diện | **Không có API Java Core tương ứng cho annotation khai báo biến cục bộ** |

Một loại annotation không khai báo `@Retention` có retention mặc định **`CLASS`**. Vì vậy, ví dụ cần reflection trên tham số phải ghi rõ `@Retention(RetentionPolicy.RUNTIME)`.

Với annotation trên khai báo biến cục bộ, đừng suy diễn rằng việc đặt `RUNTIME` bảo đảm truy xuất được qua `Method` hoặc `Parameter`: không có đối tượng reflection mô tả riêng từng biến cục bộ.

Ngoài ra, thông tin debug về tên biến cục bộ (nếu tồn tại) trong class file và thông tin annotation là **hai loại dữ liệu khác nhau**. Không thể coi việc bật tùy chọn debug của compiler là cách tự động đọc mọi annotation biến cục bộ qua reflection.

## 9. Ứng dụng thực tế và cách chọn target

### Khi dùng PARAMETER

Annotation trên tham số phù hợp với metadata gắn với **đầu vào của method/constructor**. Chẳng hạn một thư viện có thể đọc tên trường cần ánh xạ, điều kiện xác thực, quy tắc chuyển đổi hoặc giá trị yêu cầu để xử lý đầu vào.

Trong một framework, tác dụng còn cần tích hợp đúng thành phần tiêu thụ annotation. Chỉ vì một annotation có target `PARAMETER` không có nghĩa Java tự kiểm tra ràng buộc. Ví dụ các annotation đánh dấu request parameter của framework thường được framework đọc tại runtime; chúng không phải cơ chế chuẩn của Java SE.

### Khi dùng LOCAL_VARIABLE

Annotation biến cục bộ hữu ích hơn cho **công cụ phân tích mã nguồn hoặc kiểm tra tại compile time**, vì Java Core reflection không mở API trực tiếp cho biến cục bộ. Công cụ có thể dùng metadata để áp đặt quy tắc coding, cảnh báo hoặc phân tích tính chất cục bộ, tùy việc công cụ có hỗ trợ nhìn thấy và xử lý annotation ở đó.

Nếu cần đặt cấu hình để ứng dụng đọc tại runtime theo method, hãy cân nhắc mục tiêu thực tế: metadata ở cấp tham số hoặc phương thức có thể phù hợp hơn so với đặt vào một biến cục bộ rồi kỳ vọng reflection đọc được.

### Khi dùng cả hai

Nếu một metadata có cùng ý nghĩa hợp lệ ở đầu vào và tại biến tạm, định nghĩa:

```java
@Target({ElementType.PARAMETER, ElementType.LOCAL_VARIABLE})
@interface Note {
    String value();
}
```

Chỉ mở rộng `@Target` khi có mục đích rõ ràng. Cho phép nhiều target không có nghĩa công cụ xử lý annotation ở cả hai nơi theo cùng một cách.

## 10. Các lỗi phổ biến

**1. Dùng `PARAMETER` để gắn lên biến trong thân method.** Biến cục bộ cần `LOCAL_VARIABLE`; compiler sẽ từ chối annotation chỉ dành cho `PARAMETER`.

**2. Dùng `LOCAL_VARIABLE` để gắn lên tham số.** Tham số method/constructor là khai báo khác biến cục bộ, dù syntax đều có kiểu và tên.

**3. Nghĩ `@Retention(RUNTIME)` cho biến cục bộ nghĩa là reflection sẽ đọc được biến.** Reflection Java Core có API cho `Parameter`, không có API tương đương cho local variable declaration.

**4. Cho rằng annotation `PARAMETER` có thể lấy qua `Method.getAnnotation(...)`.** Annotation trên **tham số** cần truy cập `Method.getParameters()[i]` rồi đọc annotation của `Parameter`. `Method.getAnnotation` hỏi về annotation trực tiếp trên **method**, không phải tham số.

**5. Nhầm annotation khai báo với annotation kiểu `TYPE_USE`.** Xem `@Target` của loại annotation và dùng `getAnnotatedType()` khi thực sự muốn đọc annotation trên type-use runtime có hỗ trợ.

**6. Tưởng giá trị trong annotation tự validate.** `@InputName("email")` chỉ cung cấp chuỗi metadata. Không có validation nếu không có bộ xử lý diễn giải chuỗi đó.

**7. Trông chờ `Parameter.getName()` luôn trả tên gốc.** Tên tham số có thể được thay bằng tên tổng hợp `arg0`; nếu cần tên nguồn, dùng cờ biên dịch và cơ chế phù hợp, hoặc dùng tên khai báo riêng trong giá trị annotation.

**8. Cho rằng annotation ở tham số sẽ tự áp dụng cho mọi biến gán từ tham số ấy.** Metadata không tự lan truyền theo dữ liệu được truyền hoặc gán; một local variable là khai báo độc lập.

**9. Bỏ qua `@Target` trong định nghĩa annotation.** Điều này có thể dẫn đến annotation dùng ở vị trí không dự kiến. Khai báo các `ElementType` cần thiết giúp compiler kiểm soát cách dùng.

**10. Quên đọc `@Retention` trước khi viết logic reflection.** Annotation không có retention `RUNTIME` sẽ không được `Parameter.getAnnotation(...)` cung cấp theo cơ chế runtime reflection thông thường.

## 11. Bài tập thực hành

1. Trong ví dụ `ParameterLocalTargetDemo`, thêm tham số `@InputName("prefix") String prefix` vào `greet`. Sửa `getDeclaredMethod` và đoạn reflection để in cả hai tên metadata. Đừng quên cập nhật phương thức gọi.
2. Thử gắn `@LocalHint("wrong")` lên tham số `name`. Ghi nhận lỗi biên dịch và giải thích bằng `@Target(LOCAL_VARIABLE)`.
3. Thử gắn `@InputName("wrong")` lên biến `greeting`. Giải thích vì sao lỗi phát sinh dù biến có cùng kiểu `String`.
4. Thay `@Retention(RetentionPolicy.RUNTIME)` của `InputName` thành `CLASS`. Dự đoán kết quả `parameter.getAnnotation(InputName.class)` và sửa chương trình để xử lý trường hợp không tìm thấy.
5. Thêm một biến `@Track("other local") int count = name.length();` trong `greet`. Hãy giải thích tại sao chỉ đọc `Method.getParameters()` không thể tìm annotation trên `count`.
6. Định nghĩa một annotation `@TypedLabel` chỉ có `TYPE_USE`, rồi thử chú thích kiểu `String` của tham số và biến cục bộ. So sánh khái niệm annotation trên *declaration* với annotation trên *type-use*.

**Điểm cần nhớ:** `PARAMETER` mô tả **khai báo tham số**; `LOCAL_VARIABLE` mô tả **khai báo biến cục bộ**. Java compiler kiểm tra `@Target` cho cả hai, nhưng khả năng đọc bằng reflection không giống nhau. Chọn target theo đối tượng cần mô tả và theo thành phần thực sự sử dụng metadata.
