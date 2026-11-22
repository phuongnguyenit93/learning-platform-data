# Reflection trong Java: Là gì và vấn đề cần giải quyết?

Reflection (phản chiếu) là cơ chế cho phép chương trình Java **tìm hiểu cấu trúc của kiểu dữ liệu và thao tác với một số thành phần của kiểu đó khi chương trình đang chạy**. Thay vì chỉ gọi trực tiếp những lớp, phương thức đã được viết rõ trong mã nguồn, chương trình có thể tra cứu thông tin từ một đối tượng `Class<?>`, tìm constructor/phương thức/field theo tên hoặc đặc điểm, rồi tạo đối tượng, gọi phương thức hay truy cập giá trị khi phù hợp.

Bài này tập trung vào **lý do Reflection tồn tại, cách tư duy về nó, quy trình sử dụng cơ bản và chi phí đánh đổi**. Mục tiêu là hiểu khi nào cần một cơ chế động; chưa cần dùng Reflection để can thiệp sâu vào thành phần `private`.

## 1. Vấn đề: mã nguồn không phải lúc nào cũng biết trước mọi kiểu

Với Java thông thường, lập trình viên viết rõ kiểu và lời gọi:

```java
Greeter greeter = new Greeter();
String message = greeter.sayHello("An");
```

Compiler kiểm tra rằng `Greeter` tồn tại và có phương thức `sayHello(String)`. Đây là cách nên ưu tiên vì rõ ràng, được kiểm tra kiểu lúc biên dịch và dễ bảo trì.

Nhưng có những chương trình **chỉ biết phải xử lý lớp nào tại runtime**:

- Một thư viện chuyển đối tượng thành JSON cần biết đối tượng thực tế có những thuộc tính nào.
- Một bộ chạy kiểm thử cần tìm các phương thức được đánh dấu bằng annotation và gọi từng phương thức phù hợp.
- Một container dependency injection cần tìm constructor hoặc metadata để tạo và nối các đối tượng.
- Một hệ thống plugin có thể nhận tên lớp/cấu hình do người dùng chọn sau khi chương trình đã được biên dịch.
- Một công cụ quan sát chương trình cần in tên lớp, phương thức hoặc field mà không viết riêng cho từng lớp.

Ví dụ, khi đang viết thư viện JSON, tác giả không thể biết trước toàn bộ lớp `Customer`, `Order`, `Product` ... mà ứng dụng tương lai sẽ đưa vào. Viết `if/else` cho mọi lớp không khả thi. Thư viện cần một cách chung để **khám phá metadata của bất kỳ kiểu được hỗ trợ** và xử lý theo quy tắc.

Reflection giải quyết chính nhu cầu đó: **làm việc với cấu trúc chương trình khi cấu trúc cụ thể chỉ được xác định lúc chạy**.

## 2. Reflection là gì?

Reflection API thuộc chủ yếu về:

- `java.lang.Class`: đại diện runtime của một kiểu Java và là điểm bắt đầu để khám phá metadata.
- `java.lang.reflect`: các đối tượng mô tả thành phần của kiểu, tiêu biểu `Constructor`, `Method`, `Field`, `Modifier`.
- `java.lang.annotation` và `java.lang.reflect.AnnotatedElement`: hỗ trợ tra cứu annotation tại runtime khi annotation được khai báo với retention phù hợp.

Một đối tượng thông thường biểu diễn **dữ liệu/trạng thái**, còn `Class<?>` biểu diễn **thông tin về kiểu** của đối tượng đó. Ví dụ:

```java
String text = "Hello";
Class<?> type = text.getClass();
System.out.println(type.getName()); // java.lang.String
```

Ba cách thường gặp để có `Class<?>`:

| Cách | Khi nào dùng | Lưu ý |
| --- | --- | --- |
| `MyType.class` | Biết kiểu ngay khi viết mã | Không cần có instance; được compiler kiểm tra tên kiểu |
| `value.getClass()` | Đang có một đối tượng và muốn biết lớp thực tế | `value` không được là `null` |
| `Class.forName("com.example.MyType")` | Có tên lớp dạng chuỗi ở runtime | Có thể phát sinh `ClassNotFoundException`; biến thể một tham số có thể kích hoạt khởi tạo lớp |

Reflection **không tự động biến một chuỗi bất kỳ thành mã Java**, và cũng không có nghĩa là luôn được phép truy cập mọi thành phần nội bộ. Nó cung cấp metadata cùng các thao tác động trong giới hạn access control, module system và môi trường chạy.

### Quan hệ giữa lớp, đối tượng và metadata

```text
Mã đã biên dịch + lớp được nạp bởi ClassLoader
                      |
                      v
                 Class<?>          (metadata của kiểu)
                 /   |   \
                /    |    \
         Constructor Method Field  (mô tả thành phần)
                |       |
                v       v
        Tạo đối tượng   Gọi phương thức / đọc, ghi field
```

Cùng một lớp có thể tạo ra nhiều instance; chúng có trạng thái riêng nhưng cùng chia sẻ thông tin về định nghĩa kiểu. `Class<?>` không chứa bản sao độc lập của dữ liệu từng instance.

## 3. Reflection hoạt động theo những bước nào?

1. **Xác định kiểu cần xử lý**: nhận `Class<?>` từ `.class`, `getClass()` hoặc tên lớp.
2. **Khám phá metadata**: đọc tên lớp, superclass, interface, annotation; tìm constructor, method, field phù hợp.
3. **Lựa chọn thành phần**: ví dụ chọn phương thức tên `sayHello` có đúng một tham số `String`. Tên đơn thuần có thể chưa đủ vì Java cho phép overload.
4. **Thực hiện thao tác động nếu cần**: tạo instance bằng `Constructor.newInstance(...)`, gọi bằng `Method.invoke(...)`, hoặc đọc field bằng `Field.get(...)`.
5. **Xử lý rủi ro runtime**: tên không tồn tại, sai chữ ký, sai đối tượng nhận lời gọi, thiếu quyền truy cập, code được gọi ném exception...

Một số phương thức thường dùng:

| Nhu cầu | API ví dụ | Ý nghĩa |
| --- | --- | --- |
| Đọc tên kiểu | `clazz.getName()`, `clazz.getSimpleName()` | Tên đầy đủ hoặc tên ngắn |
| Tìm phương thức public | `clazz.getMethod(name, parameterTypes...)` | Tìm cả phương thức public được kế thừa |
| Xem phương thức khai báo trực tiếp | `clazz.getDeclaredMethods()` | Bao gồm cả phương thức non-public được khai báo trong lớp, không tự bao gồm inherited |
| Tìm constructor | `clazz.getDeclaredConstructor(parameterTypes...)` | Constructor được khai báo phù hợp |
| Tìm field | `clazz.getDeclaredField(name)` | Field được khai báo trong lớp |
| Xem annotation runtime | `clazz.getAnnotation(SomeAnnotation.class)` | Đọc annotation có `RetentionPolicy.RUNTIME` nếu hiện diện |

Phân biệt `getMethod` với `getDeclaredMethod`: cách thứ nhất chỉ tìm thành phần `public` (bao gồm inherited), cách thứ hai tìm thành phần **được khai báo trong lớp hiện tại** bất kể mức truy cập, nhưng việc tìm thấy metadata **không đồng nghĩa** việc được phép gọi/truy cập.

## 4. Ví dụ Java 17+: tìm và gọi phương thức khi đang chạy

Tạo một file tên **`ReflectionIntro.java`**:

```java
import java.lang.reflect.Method;

public class ReflectionIntro {

    public static class Greeter {
        public Greeter() {
        }

        public String sayHello(String name) {
            return "Xin chào, " + name + "!";
        }
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        // 1. Lấy metadata của lớp cần làm việc.
        Class<?> type = Greeter.class;
        System.out.println("Lớp: " + type.getSimpleName());

        // 2. Tạo đối tượng qua constructor không tham số.
        Object instance = type.getDeclaredConstructor().newInstance();

        // 3. Tra cứu chính xác phương thức public sayHello(String).
        Method method = type.getMethod("sayHello", String.class);

        // 4. Gọi phương thức trên đối tượng vừa tạo.
        Object result = method.invoke(instance, "An");
        System.out.println("Phương thức: " + method.getName());
        System.out.println("Kết quả: " + result);
    }
}
```

Biên dịch và chạy (có JDK 17 trở lên):

```bash
javac ReflectionIntro.java
java ReflectionIntro
```

Kết quả chuẩn:

```text
Lớp: Greeter
Phương thức: sayHello
Kết quả: Xin chào, An!
```

**Giải thích theo trình tự:**

- `Greeter.class` cho biết runtime đang thao tác với lớp nào; kiểu biến là `Class<?>` vì đoạn xử lý muốn làm việc với metadata chung.
- `getDeclaredConstructor()` tìm constructor không tham số. `newInstance()` tạo một `Greeter` thực sự; biến `instance` được khai báo `Object` vì lời gọi động có thể trả về nhiều kiểu.
- `getMethod("sayHello", String.class)` tìm phương thức `public` theo **tên + kiểu tham số**. Nếu đổi tên hoặc đổi chữ ký, việc tìm kiếm sẽ lỗi tại runtime.
- `invoke(instance, "An")` gọi phương thức trên instance. Vì `Method.invoke` trả về `Object`, người gọi có thể phải kiểm tra và ép kiểu kết quả để dùng tiếp.

Ở đây compiler **không cần thấy lời gọi** `instance.sayHello("An")`. Việc xác định phương thức được dời sang runtime. Tuy nhiên ví dụ vẫn dùng `Greeter.class` để dễ hiểu; trong ứng dụng thật, biến `type` có thể đến từ một cấu hình/plugin và không biết trước ở mã của framework.

### So sánh lời gọi thông thường với lời gọi động

| Tiêu chí | Gọi trực tiếp | Dùng Reflection |
| --- | --- | --- |
| Cú pháp | `greeter.sayHello("An")` | `method.invoke(greeter, "An")` |
| Chọn phương thức | Compiler giải quyết từ mã nguồn và kiểu khai báo | Chương trình tra cứu `Method` ở runtime |
| Sai tên/chữ ký | Thường bị báo khi biên dịch | Có thể ném exception khi chạy |
| Kiểu kết quả | `String` đã biết | Giá trị trả về từ `invoke` là `Object` |
| Khả năng xử lý kiểu chưa biết trước | Giới hạn bởi thiết kế API tĩnh | Linh hoạt hơn nhờ metadata |
| Tính đơn giản, kiểm tra kiểu và tối ưu | Thường tốt hơn | Phức tạp và dễ lỗi hơn |

Reflection **bổ sung** cho gọi phương thức thông thường; nó không khiến thiết kế hướng đối tượng, interface hay đa hình trở nên lỗi thời.

## 5. Năm tình huống Reflection thật sự có ích

**1. Thư viện serialization/deserialization.** Một serializer có thể duyệt field/getter và annotation của lớp runtime để ánh xạ dữ liệu. Framework thực tế có thể kết hợp Reflection với accessor đã sinh hoặc những tối ưu khác; không phải mọi lần xử lý JSON đều bắt buộc dùng Reflection.

**2. Dependency injection và cấu hình dựa trên annotation.** Một container có thể tìm class/constructor được khai báo và chọn cách khởi tạo theo metadata, sau đó giải quyết dependency. Cấu trúc này cho phép thêm thành phần mới mà không phải viết từng lời gọi `new` vào container.

**3. Test runner.** JUnit và công cụ tương tự có thể phát hiện phương thức kiểm thử thông qua annotation rồi thực thi trong quy trình chung. Annotation muốn được tìm trực tiếp bằng Reflection tại runtime cần được giữ lại ở runtime; không phải annotation nào cũng như vậy.

**4. Plugin / hệ thống cấu hình mở rộng.** Tên lớp cụ thể có thể lấy từ cấu hình, được load và kiểm tra trước khi sử dụng. Nếu plugin có contract ổn định, nên tiếp tục dựa trên interface để gọi chức năng chính; Reflection có thể chỉ phục vụ bước khám phá/khởi tạo.

**5. Công cụ phân tích/debug.** Một công cụ có thể trình bày tên lớp, danh sách method/field và annotation để giúp quan sát mã đang chạy. Việc liệt kê metadata không nhất thiết phải gọi phương thức hay thay đổi trạng thái đối tượng.

Điểm chung: **code hạ tầng tổng quát cần hiểu kiểu dữ liệu mà nó chưa biết khi được viết ra**.

## 6. Những giới hạn và đánh đổi cần hiểu ngay từ đầu

### Lỗi chuyển từ compile time sang runtime

Với gọi trực tiếp, IDE/compiler thường phát hiện phương thức không tồn tại. Với Reflection, tên thường được lưu bằng chuỗi nên `getMethod("syaHello", String.class)` vẫn biên dịch nhưng sẽ ném `NoSuchMethodException` khi chạy.

Các lỗi cần phân biệt:

- `ClassNotFoundException`: không tìm thấy lớp theo tên ở `Class.forName`.
- `NoSuchMethodException` / `NoSuchFieldException`: không tìm thấy thành phần cần tra cứu.
- `IllegalAccessException` hoặc `InaccessibleObjectException`: vấn đề quyền truy cập/strong encapsulation tùy API và thời điểm.
- `IllegalArgumentException`: đối tượng nhận lời gọi hoặc số lượng/kiểu đối số không thích hợp.
- `InvocationTargetException`: method/constructor được gọi **đã ném exception**; xem `getCause()` để biết nguyên nhân bên trong.

Ví dụ ở trên khai báo `throws ReflectiveOperationException` để giữ trọng tâm ở cơ chế, không phải mẫu xử lý lỗi production. Trong chương trình thực tế, hãy bổ sung xử lý ngoại lệ phù hợp với contract của ứng dụng và ghi log có ngữ cảnh.

### Encapsulation và Java Module System (JPMS)

Tìm thấy field/method `private` qua `getDeclaredField` hoặc `getDeclaredMethod` **không có nghĩa** được tự ý truy cập. `setAccessible(true)` có thể bị từ chối, đặc biệt với package không được `opens` trong module có tên; không nên xem đây là cách vượt mọi ranh giới bảo vệ. Ứng dụng nên ưu tiên API `public` và contract đã thiết kế rõ. Trong Java modules, `exports` phục vụ truy cập API thông thường, còn `opens` cho phép deep reflection tới package được chỉ định khi cần.

### Hiệu năng

Tra cứu metadata, kiểm tra truy cập, đóng gói/unbox tham số và lời gọi động có thể gây chi phí so với lời gọi trực tiếp; JVM có tối ưu Reflection nhưng không nên mặc định mọi lời gọi đều ngang nhau. Tránh lặp lại tra cứu cùng một `Method` trong vòng lặp nóng nếu có thể cache metadata. Chỉ benchmark khi có vấn đề hiệu năng thực tế; lựa chọn kiến trúc không nên dựa trên một con số benchmark không có ngữ cảnh.

### Khả năng bảo trì, refactor và bảo mật

Tên class/method dưới dạng chuỗi thường không được công cụ refactor kiểm tra đầy đủ. Dùng Reflection trên dữ liệu do người dùng cung cấp mà không giới hạn danh sách lớp/hành động được phép có thể dẫn đến thực thi hành vi ngoài dự kiến. Nếu cần nhận class từ cấu hình, hãy xác thực danh sách được phép, kiểm tra interface/contract, giới hạn quyền và xử lý lỗi rõ ràng.

Ở một số môi trường tối ưu theo mô hình đóng (ví dụ native image), các kiểu hoặc thành phần truy cập động có thể cần được đăng ký metadata/cấu hình build theo công cụ đang dùng.

## 7. Khi nào nên ưu tiên giải pháp khác?

Nếu chương trình đã biết các kiểu và hành vi từ đầu, hãy chọn **gọi trực tiếp, interface, polymorphism, generic hoặc factory**. Ví dụ, nhiều đối tượng cùng triển khai `Notifier` thì gọi `notifier.send(...)` qua interface đơn giản và an toàn kiểu hơn là Reflection để tìm tên phương thức `send`.

Dùng Reflection khi có **lý do động thực sự**: khám phá type/annotation chưa biết trước, khởi tạo theo metadata, tích hợp framework hoặc công cụ tổng quát. Thường nên cô lập nó ở lớp hạ tầng và trả ra một API có kiểu rõ ràng cho phần còn lại của ứng dụng.

Một cách tự kiểm tra trước khi chọn Reflection:

1. Kiểu hoặc phương thức cần gọi có biết được ngay khi viết code không? Nếu có, lời gọi trực tiếp thường tốt hơn.
2. Một interface hoặc factory có biểu diễn contract cần thiết được không? Nếu có, ưu tiên contract đó.
3. Metadata nào thật sự cần đọc, và thành phần đó có public hay được mở hợp lệ không?
4. Sai tên, sai chữ ký hoặc không có class sẽ được kiểm soát như thế nào?
5. Có thể cache metadata và giới hạn lớp/hành động được phép ở ranh giới runtime không?

## 8. Điều cần nhớ

Reflection cho Java khả năng **tự quan sát metadata và thao tác động với class, constructor, method, field tại runtime**. Nó giải quyết bài toán những thư viện/công cụ tổng quát phải xử lý các kiểu chưa biết trước khi biên dịch. Cái giá là giảm kiểm tra kiểu tại compile time, thêm xử lý lỗi runtime, cân nhắc quyền truy cập và khả năng bảo trì/hiệu năng.

Hãy nhớ công thức: **chỉ cần hành vi cụ thể → gọi trực tiếp qua contract; cần khám phá cấu trúc động → cân nhắc Reflection và kiểm soát chặt ranh giới của nó**.

### Tự kiểm tra hiểu bài

- Vì sao một thư viện JSON không thể viết sẵn lời gọi tới mọi lớp của ứng dụng?
- Sự khác nhau giữa `Greeter.class`, `obj.getClass()` và `Class.forName(...)` là gì?
- Vì sao `getMethod("sayHello", String.class)` phải chỉ rõ kiểu tham số?
- Vì sao tìm thấy một field `private` chưa đảm bảo có thể đọc field đó?
- Trong dự án có interface ổn định, tại sao nên gọi qua interface sau bước khám phá plugin?
