# Chính sách CLASS mặc định khi không có @Retention trong Java

## 1. Quy tắc cốt lõi

Khi định nghĩa một annotation bằng `@interface` mà **không khai báo meta-annotation `@Retention`**, Java áp dụng **chính sách lưu giữ mặc định `RetentionPolicy.CLASS`**.

```java
@interface InternalMarker {
    String value();
}
```

`InternalMarker` không ghi `@Retention(...)`, nhưng theo quy tắc của Java, các lần sử dụng nó được xử lý như annotation có chính sách `CLASS`: thông tin annotation thường được trình biên dịch ghi vào file `.class`, còn **Java Reflection API tại runtime không trả về annotation đó bằng `getAnnotation`, `getDeclaredAnnotations` hoặc `isAnnotationPresent`**.

Việc không có `@Retention` **không** đồng nghĩa `SOURCE` (chỉ tồn tại trong mã nguồn) hoặc `RUNTIME` (đọc được qua reflection). Mặc định chính xác là **`CLASS`**.

Cần tách ba vấn đề:

1. **Nguồn khai báo:** `@interface` định nghĩa một loại annotation và các phần tử của nó.
2. **Retention policy:** quyết định annotation được giữ qua giai đoạn nào.
3. **Bộ xử lý:** compiler, công cụ phân tích bytecode hoặc chương trình runtime có thể làm gì với metadata đó.

`CLASS` mô tả vòng đời metadata; nó **không tự sinh hành vi nghiệp vụ** và cũng không bảo đảm có thể truy cập qua reflection.

## 2. Ba chính sách SOURCE, CLASS và RUNTIME

Java SE định nghĩa `java.lang.annotation.RetentionPolicy` với ba giá trị:

| Chính sách | Metadata trong source/compile time | Có trong file `.class` do compiler chuẩn tạo? | Đọc bằng reflection Java thông thường tại runtime? |
| --- | --- | --- | --- |
| `SOURCE` | Có | Không, theo chính sách retention | Không |
| `CLASS` | Có | Có, trừ các ngoại lệ theo loại đích áp dụng; JVM không bắt buộc giữ nó để phục vụ runtime | Không |
| `RUNTIME` | Có | Có | Có, ở những vị trí có API reflection tương ứng |

**`CLASS` là mặc định** khi thiếu khai báo `@Retention`. Trong một annotation thuộc các vị trí khai báo thường gặp như `TYPE`, `METHOD`, `FIELD`, dữ liệu này được biên dịch thành metadata class-file. Với các đích đặc biệt như annotation khai báo **biến cục bộ** (`LOCAL_VARIABLE`), đừng suy rộng thành cam kết mọi annotation CLASS sẽ luôn được lưu trong class file theo cùng một dạng.

Nói “JVM không bắt buộc giữ annotation CLASS tại runtime” là quy định về retention; nói “Java reflection không truy xuất nó như RUNTIME annotation” là điều cần nhớ khi viết code.

### 2.1. Cú pháp dùng @Retention

```java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.SOURCE)
@interface SourceMarker {}

@Retention(RetentionPolicy.CLASS)
@interface ClassMarker {}

@Retention(RetentionPolicy.RUNTIME)
@interface RuntimeMarker {}

@interface DefaultMarker {} // Tương đương CLASS về retention policy.
```

Các khai báo này hợp lệ trong Java 17+. `RetentionPolicy` là enum thuộc Java SE; `@Retention` là meta-annotation đặt trên **định nghĩa annotation type**, không đặt lên một method để “đổi retention” của method đó.

Viết `@Retention(RetentionPolicy.CLASS)` là cách khai báo **tường minh**. Bỏ hẳn `@Retention` trên `DefaultMarker` làm quy tắc mặc định có hiệu lực. Hai trường hợp có cùng chính sách lưu giữ, nhưng **metadata về chính việc có khai báo `@Retention` hay không thì khác**.

### 2.2. Meta-annotation @Retention không có nghĩa là giá trị của annotation

Ví dụ:

```java
@Retention(RetentionPolicy.RUNTIME)
@interface Visible {
    String value();
}

@Visible("hello")
class Feature {}
```

Ở đây `@Retention` cấu hình **loại `Visible`**; `@Visible("hello")` là **một lần sử dụng annotation** trên `Feature`. Thay đổi chính sách retention phải sửa khai báo của annotation type (`Visible`), không phải thêm `@Retention` trên class sử dụng.

## 3. Tại sao CLASS khác RUNTIME?

Một file Java thường đi qua ba giai đoạn:

```text
Mã nguồn .java
     |
     | javac đọc khai báo annotation và kiểm tra cú pháp/target/giá trị
     v
File bytecode .class
     |
     | JVM nạp class; thư viện/công cụ có thể xử lý metadata
     v
Chương trình đang chạy và Reflection API
```

Với `SOURCE`, compiler không lưu các lần sử dụng annotation vào class file theo chính sách retention; công cụ xử lý mã nguồn vẫn có thể quan tâm tới chúng.

Với `CLASS`, compiler ghi annotation vào class file ở những vị trí được hỗ trợ, nhưng **reflection của Java SE không cung cấp nó như annotation runtime**.

Với `RUNTIME`, metadata được giữ để **các API reflection tương ứng** đọc được. Ví dụ annotation có `@Target(METHOD)` và `RUNTIME` có thể được truy vấn bằng `Method.getAnnotation(...)`.

Một câu dễ nhớ:

> Annotation không có `@Retention` thường vẫn tồn tại trong bytecode, nhưng không xuất hiện khi hỏi Java reflection thông thường về annotation tại runtime.

Điều này giải thích vì sao “mở file `.class` thấy annotation” và “`method.getAnnotation(...)` trả về annotation” là hai quan sát khác nhau.

### 3.1. Tên thuộc tính class-file giúp quan sát sự khác biệt

Trong class file do `javac` tạo, annotation đặt trên khai báo method/class thường được thể hiện qua những thuộc tính như:

- `RuntimeVisibleAnnotations`: lưu các annotation có `RUNTIME` retention để runtime reflection có thể nhìn thấy ở vị trí hỗ trợ.
- `RuntimeInvisibleAnnotations`: lưu những annotation `CLASS` trên khai báo; tên “Invisible” ở đây nói đến khả năng hiển thị cho runtime reflection, **không có nghĩa bytecode không chứa annotation**.

Annotation `SOURCE` không được đưa vào các thuộc tính này theo chính sách retention. Ngoài ra còn có các loại attribute liên quan parameter annotations và type annotations tùy vị trí. Cần phân biệt chúng với các annotation gắn trực tiếp trên một method.

## 4. Ví dụ Java 17+ chạy độc lập: không có @Retention là CLASS

Tạo file **DefaultRetentionDemo.java** với toàn bộ nội dung dưới đây. Các annotation được khai báo cùng một file nhằm giữ ví dụ đơn giản, không cần dependency ngoài JDK.

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;

@Target(ElementType.METHOD)
@interface DefaultTag {
    String value();
}

@Retention(RetentionPolicy.CLASS)
@Target(ElementType.METHOD)
@interface ClassTag {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface RuntimeTag {
    String value();
}

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.METHOD)
@interface SourceTag {
    String value();
}

public class DefaultRetentionDemo {
    @DefaultTag("default")
    @ClassTag("class")
    @RuntimeTag("runtime")
    @SourceTag("source")
    public void execute() {}

    public static void main(String[] args)
            throws NoSuchMethodException {
        Method method = DefaultRetentionDemo.class
                .getDeclaredMethod("execute");

        System.out.println(method.isAnnotationPresent(DefaultTag.class));
        System.out.println(method.isAnnotationPresent(ClassTag.class));
        System.out.println(method.isAnnotationPresent(RuntimeTag.class));
        System.out.println(method.isAnnotationPresent(SourceTag.class));

        RuntimeTag runtime = method.getAnnotation(RuntimeTag.class);
        System.out.println(runtime.value());
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên tại thư mục chứa file:

```bash
javac DefaultRetentionDemo.java
java DefaultRetentionDemo
```

Kết quả stdout:

```text
false
false
true
false
runtime
```

**Vì sao có kết quả này?**

1. `@DefaultTag` **không khai báo `@Retention`**, nên dùng chính sách mặc định `CLASS`. Reflection trả về `false` dù annotation đã được dùng trong source.
2. `@ClassTag` có khai báo `@Retention(CLASS)` tường minh. Nó cũng không hiển thị bằng reflection, nên in `false`.
3. `@RuntimeTag` có `@Retention(RUNTIME)`. Vì gắn trực tiếp lên method `execute()`, reflection trả về `true` và lấy được giá trị `"runtime"`.
4. `@SourceTag` có `@Retention(SOURCE)`. Không có runtime annotation để reflection đọc, nên in `false`.
5. `Method.getDeclaredMethod("execute")` trả về đúng phương thức không tham số; không yêu cầu thêm cờ compiler như `-parameters`.

Bốn annotation khác loại cùng được viết trên một method. `@Target(METHOD)` khiến compiler kiểm tra vị trí sử dụng; **`@Target` không thay đổi retention** của từng loại.

### 4.1. Xem CLASS annotation nằm trong bytecode

Sau khi biên dịch, chạy:

```bash
javap -v DefaultRetentionDemo
```

Trong phần metadata của `execute()`, có thể tìm các nhãn **`RuntimeVisibleAnnotations`** và **`RuntimeInvisibleAnnotations`**. Công cụ `javap` thuộc JDK hiển thị thông tin phân tích class file:

- `RuntimeVisibleAnnotations` liên quan đến `RuntimeTag`.
- `RuntimeInvisibleAnnotations` liên quan đến **cả `DefaultTag` và `ClassTag`**.
- `SourceTag` không có mặt trong class file ở phần annotation của method.

Không nên coi số thứ tự constant pool hoặc thứ tự dòng in từ `javap -v` là API ổn định: chúng có thể thay đổi theo compiler/JDK. Điều cần quan sát là **annotation CLASS có metadata trong class file, nhưng không có trong kết quả reflection của chương trình**.

### 4.2. Thử chỉ bỏ @Retention khỏi RuntimeTag

Nếu đổi:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface RuntimeTag {
    String value();
}
```

thành:

```java
@Target(ElementType.METHOD)
@interface RuntimeTag {
    String value();
}
```

thì `RuntimeTag` chuyển sang mặc định `CLASS`. Khi biên dịch và chạy lại, `method.getAnnotation(RuntimeTag.class)` trả về `null`. Ví dụ gốc gọi `runtime.value()` sẽ phát sinh `NullPointerException` nếu không sửa phần xử lý.

Vì vậy, khi đọc metadata bằng reflection, hãy **kiểm tra null** hoặc dùng `isAnnotationPresent` theo ngữ cảnh. Nếu chủ đích là ứng dụng runtime luôn đọc được, khai báo `RUNTIME` tường minh từ đầu.

## 5. Dùng CLASS mặc định trong trường hợp nào?

Không phải annotation nào cũng cần được truy vấn bởi ứng dụng khi chạy. Chính sách `CLASS` phù hợp khi muốn lưu metadata trong class file nhưng không cần expose nó qua reflection Java thông thường.

Ví dụ các nhóm nhu cầu có thể liên quan:

- **Công cụ phân tích hoặc biến đổi bytecode**: một công cụ có thể đọc class file và quan tâm tới các annotation được lưu giữ trong đó.
- **Quy ước mô tả nội bộ ở mức class file**: metadata cần theo artifact đã biên dịch cho một quy trình build hoặc phân tích, nhưng không cần truy vấn trực tiếp qua `Method.getAnnotation`.
- **Annotation chỉ cần xử lý tại thời điểm biên dịch**: nếu mọi thông tin chỉ cần trong lúc compiler đọc source thì `SOURCE` có thể thích hợp hơn, nhưng `CLASS` vẫn có ý nghĩa khi cần giữ metadata sau biên dịch.

Điểm quan trọng: chỉ vì annotation là `CLASS` **không có nghĩa tự nhiên sẽ có một công cụ xử lý nó**. Công cụ nhận biết và đọc annotation phải được thiết kế hoặc cấu hình riêng.

### 5.1. Khi nào nên chọn RUNTIME?

Chọn `@Retention(RetentionPolicy.RUNTIME)` khi thiết kế annotation mà **chương trình đang chạy cần đọc bằng reflection**, chẳng hạn custom runtime configuration hoặc framework introspection. Ví dụ:

```java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.RUNTIME)
@interface FeatureFlag {
    boolean enabled() default true;
}
```

Đây chỉ là định nghĩa metadata. Để có tác dụng bật/tắt tính năng, code runtime vẫn cần lấy `FeatureFlag` và áp dụng giá trị `enabled()`. Việc thêm `RUNTIME` **chỉ cho phép truy cập**, không khiến Java tự bật/tắt tính năng.

### 5.2. Khi nào nên chọn SOURCE?

Chọn `@Retention(RetentionPolicy.SOURCE)` nếu annotation chỉ phục vụ compiler hoặc công cụ xử lý source và không cần nằm trong class file. Một ví dụ Java SE là `@Override`, được compiler kiểm tra trong quá trình biên dịch.

Tuy nhiên, **đừng suy đoán chính sách chỉ từ mục đích**: hãy xem định nghĩa thật của annotation. Nếu một thư viện tự định nghĩa annotation mà bỏ `@Retention`, chính sách của nó vẫn mặc định là `CLASS`, bất kể tên annotation có vẻ dùng cho runtime.

## 6. Thiếu @Retention và khai báo @Retention(CLASS) có hoàn toàn giống nhau?

Về **chính sách retention của các lần sử dụng annotation**, hai định nghĩa sau có cùng ý nghĩa:

```java
@interface A {}

@Retention(RetentionPolicy.CLASS)
@interface B {}
```

Trong hai trường hợp, compiler đều áp dụng `CLASS` policy cho annotation tương ứng. Nhưng về **khai báo annotation type**, chúng không giống hệt:

- `A` không có meta-annotation `@Retention` được khai báo.
- `B` có meta-annotation `@Retention(CLASS)` được khai báo tường minh.

Bởi `@Retention` là annotation có `RUNTIME` retention, mã reflection kiểm tra trực tiếp trên **định nghĩa annotation type** có thể phân biệt:

```java
// Mã minh họa trong ngữ cảnh đã định nghĩa A và B:
boolean aHasRetention = A.class.isAnnotationPresent(Retention.class); // false
boolean bHasRetention = B.class.isAnnotationPresent(Retention.class); // true
```

Hai giá trị khác nhau **không làm thay đổi chính sách mặc định**. Nếu xây công cụ đọc định nghĩa annotation, cần hiểu rằng `@Retention` vắng mặt nghĩa là `CLASS`, chứ không phải “không có chính sách”.

Với các dự án lớn, đôi khi ghi `@Retention(CLASS)` rõ ràng giúp người đọc không phải nhớ giá trị mặc định; việc bỏ nó vẫn hoàn toàn hợp lệ về ngôn ngữ.

## 7. CLASS retention, @Target và @Inherited là những vấn đề khác nhau

Một annotation có thể có nhiều meta-annotation, nhưng **mỗi cái trả lời một câu hỏi khác**.

| Meta-annotation | Trả lời câu hỏi | Có đổi mặc định CLASS không? |
| --- | --- | --- |
| `@Retention` | Giữ annotation đến giai đoạn nào? | Có, nếu chỉ định `SOURCE` hoặc `RUNTIME`; hoặc khai báo rõ `CLASS` |
| `@Target` | Được gắn lên loại khai báo/type-use nào? | Không |
| `@Documented` | Công cụ tạo tài liệu API có nên trình bày annotation không? | Không |
| `@Inherited` | Trong giới hạn kế thừa annotation trên class, tra cứu từ superclass có thể áp dụng không? | Không |
| `@Repeatable` | Một loại annotation có được lặp trên cùng phần tử không? | Không |

Ví dụ:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@interface InternalType {}
```

`InternalType` có `@Target(TYPE)` nhưng **không có `@Retention`**, nên vẫn là `CLASS`. Có thêm `@Documented` hay `@Inherited` cũng không tự nâng nó thành `RUNTIME`.

Một annotation loại `CLASS` được đánh dấu `@Inherited` vẫn không thể được đọc như runtime annotation qua các phương thức reflection thường dùng, vì nó không có `RUNTIME` retention. Nếu thực sự cần hành vi truy vấn kế thừa ở runtime, hãy xem xét cả đích áp dụng, retention và quy tắc truy vấn reflection.

## 8. Một số nhầm lẫn cần tránh

### 8.1. “Không có @Retention nên không lưu ở đâu cả”

Sai. Với đa số khai báo class/method/field thông thường, **annotation không có `@Retention` được compiler lưu như annotation `CLASS` trong class file**. Muốn không lưu trong class file theo chính sách retention, hãy khai báo rõ `SOURCE`.

### 8.2. “Đã có trong file .class thì Java reflection đọc được”

Sai. `CLASS` chính là ví dụ chứng minh sự khác biệt. Công cụ phân tích class file có thể đọc những attribute dành cho `CLASS`, nhưng `Method.getAnnotation` chỉ cung cấp metadata được giữ lại cho runtime theo cơ chế reflection phù hợp.

### 8.3. “Java compiler không xử lý annotation CLASS”

Sai. Compiler phải phân giải annotation type, kiểm tra cú pháp, vị trí `@Target`, kiểu và giá trị phần tử; compiler và annotation processor được cấu hình còn có thể đọc annotation tại thời điểm biên dịch. **Không đọc được bằng reflection runtime không có nghĩa compiler bỏ qua nó.**

### 8.4. “@Retention(CLASS) áp dụng cho mọi annotation trong một file”

Sai. `@Retention` được áp dụng cho **từng khai báo annotation type**, không phải một thiết lập global cho file, package hay project. Hai annotation định nghĩa trong cùng file có thể có retention khác nhau.

### 8.5. “Đổi CLASS sang RUNTIME chỉ cần đổi đoạn reflection”

Sai. Chính sách retention nằm trên annotation type. Muốn chạy reflection cần định nghĩa annotation có `RUNTIME`, đồng thời phải biên dịch lại các lớp sử dụng annotation khi cần để metadata của những lần sử dụng đó được ghi với chính sách mới. Sử dụng các artifact đã biên dịch theo chính sách cũ có thể khiến metadata quan sát được không giống dự kiến.

### 8.6. “Muốn annotation hoạt động thì bắt buộc luôn dùng RUNTIME”

Sai. Những annotation được compiler hoặc công cụ build xử lý ở compile time vẫn hữu ích với `SOURCE` hoặc `CLASS`. Chỉ cần `RUNTIME` khi thành phần runtime thực sự cần truy cập metadata bằng cơ chế hỗ trợ.

### 8.7. “@Retention vắng mặt thì getAnnotation(Retention.class) trả về CLASS”

Sai. Nếu truy vấn **meta-annotation `@Retention` trên chính annotation type** mà khai báo này không có `@Retention`, `getAnnotation(Retention.class)` trả về `null`. Chính sách mặc định `CLASS` do Java định nghĩa, không phải một meta-annotation ngầm được tự thêm vào đối tượng reflection.

### 8.8. “Thêm RUNTIME là đủ cho mọi đích áp dụng”

Không chính xác. Reflection Java Core không cung cấp API duyệt khai báo **biến cục bộ** tương tự `Method`, `Field` hay `Parameter`. `@Target` và khả năng quan sát runtime phải được xem theo loại vị trí annotation; `RUNTIME` không tự tạo một API reflection mới.

## 9. Quy trình kiểm tra nhanh trong dự án

Khi gặp một annotation tự định nghĩa và muốn biết có thể đọc nó tại runtime hay không:

1. **Mở khai báo `@interface`.** Tìm `@Retention` trên chính kiểu annotation đó.
2. **Nếu `@Retention` vắng mặt, kết luận policy = `CLASS`.** Đừng suy từ tên annotation hoặc chức năng dự kiến.
3. **Nếu có `@Retention`, đọc đúng giá trị.** `SOURCE`, `CLASS` và `RUNTIME` khác nhau về vòng đời.
4. **Kiểm tra `@Target` và vị trí thực tế sử dụng.** API phản chiếu tương ứng có thể là `Class`, `Method`, `Field`, `Parameter` hoặc `AnnotatedType`; không phải vị trí nào cũng có đối tượng reflection trực tiếp.
5. **Kiểm tra code/công cụ tiêu thụ metadata.** Runtime reflection, annotation processor và bytecode scanner có khả năng nhìn thấy các dạng metadata khác nhau.
6. **Nếu chưa rõ, tạo ví dụ ngắn.** Dùng `javac` để biên dịch, `javap -v` để quan sát bytecode và `getAnnotation` để quan sát runtime reflection.

**Câu hỏi tự kiểm tra:** Một annotation có `@Target(METHOD)`, không có `@Retention`, được dùng trên `run()`. Điều nào đúng?

- Compiler có thể xử lý nó khi biên dịch: **Đúng**.
- Nó có retention policy `CLASS`: **Đúng**.
- Nó thường có metadata trong class file: **Đúng**.
- `runMethod.getAnnotation(ThatAnnotation.class)` chắc chắn trả về đối tượng annotation: **Sai**.
- Thêm `@Target(METHOD)` đủ để chuyển nó thành RUNTIME: **Sai**.

## 10. Bài tập thực hành

1. **Quan sát CLASS mặc định:** Biên dịch `DefaultRetentionDemo.java`, rồi chạy `javap -v DefaultRetentionDemo`. Tìm `DefaultTag` và `ClassTag` trong `RuntimeInvisibleAnnotations`. So sánh với kết quả reflection là `false` cho cả hai.
2. **Thay đổi retention:** Thêm `@Retention(RetentionPolicy.RUNTIME)` vào định nghĩa `DefaultTag`, biên dịch lại toàn bộ file và dự đoán bốn giá trị boolean in ra. Sau thay đổi, giá trị đầu tiên trở thành `true`.
3. **Thử SOURCE:** Đổi `ClassTag` thành `@Retention(SOURCE)`. Dùng `javap -v` để giải thích vì sao `ClassTag` không còn trong metadata của method.
4. **Đọc meta-annotation:** Trong một file thử nghiệm có định nghĩa `DefaultTag` và `ClassTag`, gọi `DefaultTag.class.getAnnotation(Retention.class)` và `ClassTag.class.getAnnotation(Retention.class)`. Kết quả khác nhau thế nào, và có làm khác policy của các lần sử dụng không?
5. **Bài toán thiết kế:** Bạn tạo `@BusinessRule` để một annotation processor kiểm tra source code khi build. Bạn cần dữ liệu trong file class sau biên dịch không? Nếu không, cân nhắc `SOURCE`; nếu có, cân nhắc `CLASS`. Nếu ứng dụng cần đọc bằng reflection tại runtime, chọn `RUNTIME` và giải thích phần code cần tiêu thụ metadata.

**Điểm cần nhớ:** **Không khai báo `@Retention` ⇒ `RetentionPolicy.CLASS`**. Với annotation trên khai báo thông thường, compiler giữ nó trong `.class`, nhưng Java Reflection API không coi nó là annotation có thể truy cập tại runtime. Chỉ định `@Retention(RUNTIME)` khi thực sự cần runtime reflection; chọn `SOURCE` khi chỉ cần thông tin trong giai đoạn biên dịch.
