# Chọn vòng đời Annotation theo bên xử lý và thời điểm sử dụng trong Java

## 1. Vấn đề: ai cần đọc annotation và đọc lúc nào?

Khi tự định nghĩa một annotation bằng `@interface`, ta thường có một mục tiêu cụ thể: nhắc compiler kiểm tra, hỗ trợ annotation processor sinh mã, cho công cụ phân tích file `.class`, hoặc để framework đọc cấu hình khi ứng dụng đang chạy. Những bên xử lý ấy tiếp cận metadata ở **các giai đoạn khác nhau**.

Java cho phép tác giả annotation xác định metadata được giữ lại đến đâu bằng meta-annotation `@Retention`. Ba mức chính sách là:

- `RetentionPolicy.SOURCE`: metadata chỉ cần trong mã nguồn và quá trình biên dịch; không được lưu lại trong class file.
- `RetentionPolicy.CLASS`: metadata được ghi vào class file để công cụ đọc bytecode có thể sử dụng; cơ chế reflection chuẩn không trả về nó ở runtime.
- `RetentionPolicy.RUNTIME`: metadata được ghi trong class file và có thể được các API reflection chuẩn truy cập khi chạy.

Chọn đúng retention là cách **khớp vòng đời metadata với bên thực sự tiêu thụ metadata**. Không phải annotation nào cũng cần `RUNTIME`; ngược lại, nếu một framework dùng `Class.getAnnotation(...)` thì `SOURCE` hoặc `CLASS` là chưa đủ.

Ví dụ câu hỏi cần trả lời trước khi khai báo:

> “Annotation này sẽ được đọc bởi `javac`, một annotation processor, công cụ quét `.class` sau biên dịch, hay Java reflection khi ứng dụng đang chạy?”

Câu trả lời quyết định retention phù hợp.

## 2. `@Retention` được đặt trên annotation type như thế nào?

`@Retention` thuộc package `java.lang.annotation`. Nó nhận một giá trị enum `RetentionPolicy`:

```java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.SOURCE)
@interface SourceMarker {
    String value();
}

@Retention(RetentionPolicy.CLASS)
@interface ClassMarker {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@interface RuntimeMarker {
    String value();
}
```

`@Retention(...)` phải đặt trên **định nghĩa annotation type**, không phải tùy chọn được chỉ định lại tại từng nơi sử dụng:

```java
@RuntimeMarker("checkout")
class CheckoutService {}
```

Mỗi annotation type có một chính sách retention đã được định nghĩa. Chẳng hạn, nếu `@RuntimeMarker` có `RUNTIME`, các lần sử dụng `@RuntimeMarker` đều tuân theo chính sách đó.

Khi **không khai báo `@Retention`**, mặc định của Java là **`RetentionPolicy.CLASS`**, không phải `SOURCE` và cũng không phải `RUNTIME`:

```java
@interface DefaultMarker {
    String value();
}
// Tương đương về retention với @Retention(RetentionPolicy.CLASS).
```

Nên ghi tường minh `@Retention` cho annotation tự thiết kế để người đọc không phải nhớ giá trị mặc định và để thể hiện rõ ý định của API.

## 3. Ba chính sách ứng với ba mốc vòng đời

Hình dung tiến trình phổ biến:

```text
Mã nguồn .java
    |
    | javac: parse, kiểm tra kiểu, xử lý annotation
    v
Kết quả biên dịch .class / .jar
    |
    | công cụ đọc file .class hoặc bytecode
    v
Ứng dụng nạp class và chạy trên JVM
    |
    | reflection: Class.getAnnotation(...), Method.getAnnotations(), ...
    v
Logic framework/application xử lý metadata
```

Bảng quyết định:

| Chính sách | Có trong nguồn / khi biên dịch | Được giữ trong `.class` | Đọc qua Java reflection thông thường |
|---|---|---|---|
| `SOURCE` | Có | Không | Không |
| `CLASS` | Có | Có | Không |
| `RUNTIME` | Có | Có | Có |

Bảng trên mô tả annotation trên những khai báo được hỗ trợ, ví dụ class, method hoặc field; cách lưu cụ thể cho *type-use annotations* phụ thuộc vị trí annotation trong class file.

### `SOURCE`: xong nhiệm vụ sau giai đoạn biên dịch

`SOURCE` dành cho metadata hữu ích khi compiler hoặc annotation processor đang xử lý mã nguồn, nhưng chương trình sau biên dịch không cần xem lại nó.

Ví dụ trong thư viện chuẩn, `@Override` và `@SuppressWarnings` có retention `SOURCE`: chúng phục vụ kiểm tra của compiler và không cần trở thành metadata runtime.

Chọn `SOURCE` khi các điều kiện phù hợp:

- Compiler/annotation processor cần thấy annotation **trong lượt biên dịch chứa mã nguồn đang được chú thích**.
- Không cần tìm lại annotation từ thư viện đã biên dịch chỉ còn `.class`.
- Không có bộ quét bytecode hoặc logic reflection nào phụ thuộc vào annotation sau biên dịch.

`SOURCE` không đảm bảo một annotation processor sẽ tự động chạy: processor còn phải được đăng ký, được kích hoạt trong quy trình build và được lập trình xử lý annotation.

### `CLASS`: giữ metadata trong artifact để đọc sau biên dịch

`CLASS` dành cho công cụ làm việc với bytecode hoặc class file, ví dụ một bước kiểm tra/biến đổi `.class` trong build pipeline. Metadata còn trong artifact, dù reflection chuẩn không phơi bày nó.

Chọn `CLASS` khi:

- Bộ xử lý chạy **sau khi biên dịch**, đầu vào là `.class` hoặc `.jar`, và cần đọc annotation.
- Công cụ chủ động phân tích class-file attributes hoặc dùng thư viện bytecode.
- Không cần `Class.getAnnotation(...)` hay các API tương tự trong ứng dụng lúc chạy.

`CLASS` cũng có thể phục vụ công cụ xử lý những annotation nằm trong thư viện phụ thuộc đã biên dịch, nếu công cụ có khả năng đọc metadata class file tương ứng.

Cẩn thận: **annotation tồn tại trong class file không đồng nghĩa Java reflection nhìn thấy nó**. Công cụ đọc trực tiếp bytecode và reflection tiêu chuẩn có cơ chế truy cập khác nhau.

### `RUNTIME`: framework hoặc ứng dụng cần reflection

`RUNTIME` dành cho metadata cần được truy vấn bằng reflection sau khi JVM nạp class.

Ví dụ:

```java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.annotation.ElementType;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Timed {
    String name();
}
```

Một framework có thể tìm annotation `@Timed` trên method qua `Method.getAnnotation(Timed.class)`, rồi chủ động kích hoạt mã ghi thời gian. Annotation không tự đo thời gian; logic của framework mới làm việc đó.

Chọn `RUNTIME` khi bên sử dụng thực sự cần những API như:

- `Class.getAnnotation(...)` hoặc `Class.isAnnotationPresent(...)`.
- `Method.getAnnotation(...)`, `Field.getAnnotation(...)`, `Constructor.getAnnotations()`.
- `Parameter.getAnnotations()` hoặc API reflection khác cho đúng vị trí annotation.
- `AnnotatedElement.getDeclaredAnnotations()` và các biến thể tra cứu được công khai.

`RUNTIME` là mức giữ metadata dài nhất trong ba chính sách. Metadata runtime vẫn nằm trong class file, nên bộ quét bytecode thường cũng đọc được nó. Chọn `RUNTIME` nếu cần reflection; không cần đổi annotation sang `CLASS` chỉ vì một công cụ bytecode khác cũng sử dụng.

## 4. Bên xử lý nào nên chọn chính sách nào?

| Bên xử lý / yêu cầu | Thời điểm cần metadata | Retention nên cân nhắc | Vì sao |
|---|---|---|---|
| `javac` kiểm tra chú thích khi đọc nguồn | Trong biên dịch | `SOURCE` | Metadata không cần đi theo artifact |
| Annotation processor đọc trực tiếp những source file đang biên dịch | Trong biên dịch | `SOURCE` | Processor dùng mô hình phần tử được compiler cung cấp |
| Bộ sinh mã cần tìm annotation trên thư viện đã biên dịch | Bước build sau hoặc khi đọc dependency `.class` | `CLASS` hoặc `RUNTIME` | `SOURCE` đã bị loại khỏi class file |
| Bộ phân tích bytecode sau `javac` | Sau biên dịch | `CLASS` | Đủ để giữ metadata cho công cụ bytecode |
| Bytecode transformer xử lý artifact đóng gói | Build / load / transform, bằng class-file API | `CLASS` hoặc `RUNTIME` | Công cụ phải đọc class-file attributes |
| Framework gọi reflection trong ứng dụng | Runtime | `RUNTIME` | API reflection cần runtime-visible annotation |
| Runtime scanner chỉ đọc trực tiếp bytecode, không dùng reflection | Runtime nhưng trên bytes của `.class` | `CLASS` có thể đủ | Cần xác nhận scanner thực sự đọc runtime-invisible annotations |
| Không có bên xử lý cụ thể | Chưa xác định | Chưa thể quyết định bằng thời điểm | Xác định cách tiêu thụ trước khi thiết kế |

**Điểm then chốt:** chọn theo **cách bên xử lý tiếp cận metadata**, không chỉ dựa vào việc nó chạy lúc build hay runtime. Một công cụ chạy ở runtime nhưng đọc trực tiếp bytecode có thể nhìn thấy `CLASS`; ngược lại, code runtime chỉ dùng reflection chuẩn thì bắt buộc phải có `RUNTIME`.

Trong dự án thực tế, hãy kiểm tra tài liệu và cách thực thi của công cụ/framework. Chỉ thấy một annotation xuất hiện trong API không đủ để suy ra retention cần thiết nếu chưa biết ai đọc nó.

## 5. Ví dụ Java 17+ hoàn chỉnh: ba retention, cùng một class

Tạo file **`RetentionChoiceDemo.java`**:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
@interface SourceHint {
    String value();
}

@Retention(RetentionPolicy.CLASS)
@Target(ElementType.TYPE)
@interface ClassHint {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface RuntimeHint {
    String value();
}

@SourceHint("compile")
@ClassHint("bytecode")
@RuntimeHint("reflection")
class OrderHandler {
}

public class RetentionChoiceDemo {
    public static void main(String[] args) {
        Class<OrderHandler> type = OrderHandler.class;

        System.out.println("SOURCE reflection="
                + type.isAnnotationPresent(SourceHint.class));
        System.out.println("CLASS reflection="
                + type.isAnnotationPresent(ClassHint.class));
        System.out.println("RUNTIME reflection="
                + type.isAnnotationPresent(RuntimeHint.class));

        RuntimeHint hint = type.getAnnotation(RuntimeHint.class);
        System.out.println("value=" + hint.value());
    }
}
```

Lưu file và chạy bằng JDK 17 trở lên:

```bash
javac RetentionChoiceDemo.java
java RetentionChoiceDemo
```

**Stdout chính xác:**

```text
SOURCE reflection=false
CLASS reflection=false
RUNTIME reflection=true
value=reflection
```

Giải thích:

1. Cả ba annotation hợp lệ và cùng có đích `TYPE`.
2. `javac` thấy các annotation trong mã nguồn, nhưng `SourceHint` bị loại khỏi class file sau biên dịch.
3. `ClassHint` được ghi trong class file nhưng **không xuất hiện qua `isAnnotationPresent`**.
4. `RuntimeHint` được ghi lại với tính khả kiến tại runtime; `isAnnotationPresent` trả `true` và `getAnnotation` đọc `value` là `"reflection"`.

Tất cả các annotation type và `OrderHandler` đều khai báo không có modifier `public` trong cùng file; `RetentionChoiceDemo` là public class duy nhất và trùng tên file, nên ví dụ tuân thủ quy tắc Java.

**Không suy ra `SOURCE`/`CLASS` đã lỗi hoặc bị JVM xóa hoàn toàn** từ kết quả `false` của reflection. Với `CLASS`, metadata vẫn có thể tồn tại ở lớp class-file bytes; kết quả `false` chỉ phản ánh cách Java reflection chuẩn phơi bày annotation.

## 6. Kiểm tra class file với `javap -v`

Sau khi biên dịch ví dụ mục 5, dùng:

```bash
javap -v OrderHandler
```

Trong thông tin class-file chi tiết, quan sát các nhóm annotation declaration:

- `RuntimeVisibleAnnotations`: dữ liệu annotation có retention `RUNTIME`; ví dụ này chứa `RuntimeHint`.
- `RuntimeInvisibleAnnotations`: dữ liệu annotation được lưu vào class file nhưng không cần phơi bày qua reflection; ví dụ này chứa `ClassHint`.
- `SourceHint` không được ghi dưới dạng annotation trên `OrderHandler` vì retention `SOURCE`.

Tên thuộc tính class-file có thể xuất hiện trong output `javap` với ký hiệu descriptor hoặc constant-pool index. Chỉ cần nhận diện sự khác biệt giữa *Visible* và *Invisible*, không cần thuộc toàn bộ cách mã hóa class file.

Nếu dùng annotation trên vị trí **TYPE_USE**, class file có thể dùng các thuộc tính khác như `RuntimeVisibleTypeAnnotations` và `RuntimeInvisibleTypeAnnotations`. Điều này không đổi nguyên tắc lựa chọn retention; nó chỉ phản ánh những dạng annotation khác nhau trong định dạng class file.

Khi dùng `javap` hoặc thư viện đọc bytecode, cần kiểm tra **đúng class file có khai báo được chú thích**, thay vì chỉ xem file định nghĩa annotation. `@Retention` nằm trong định nghĩa annotation type; dữ liệu của một lần sử dụng nằm ở class file của thành phần được chú thích, nếu chính sách yêu cầu giữ lại.

## 7. Annotation processor và lựa chọn `SOURCE`

Một annotation processor theo API `javax.annotation.processing` làm việc trong quy trình biên dịch, truy cập thông tin chương trình qua mô hình phần tử `javax.lang.model`. Với annotation trên mã nguồn được biên dịch trong lượt đó, retention `SOURCE` là lựa chọn tự nhiên nếu kết quả xử lý không cần đọc lại metadata từ artifact.

Ví dụ định nghĩa annotation đánh dấu class cần tạo tài liệu:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
public @interface GenerateSummary {
    String value();
}
```

Đây là **nội dung minh họa cho một file riêng tên `GenerateSummary.java`**, không thuộc chương trình `RetentionChoiceDemo.java` phía trên. Một processor phù hợp có thể tìm các kiểu mang `@GenerateSummary` qua `RoundEnvironment.getElementsAnnotatedWith(GenerateSummary.class)` khi biên dịch mã nguồn sử dụng annotation.

Điều cần phân biệt:

- **Retention và thời điểm processor chạy là hai khái niệm khác nhau.** `SOURCE` không tự kích hoạt processor, không đăng ký processor và không bắt compiler sinh file.
- Processor phải được build, được cung cấp cho `javac` theo đúng cấu hình và thực sự xử lý annotation type tương ứng.
- Nếu muốn một processor hoặc một tool khác đọc annotation trên các class của một dependency **chỉ có file `.class`**, `SOURCE` không đủ vì thông tin đã bị loại khỏi artifact. Khi ấy cân nhắc `CLASS` hoặc `RUNTIME`.
- Nếu processor cũng cần tạo annotation mà framework runtime sẽ đọc trực tiếp, đó có thể là **hai loại annotation** với mục đích khác nhau hoặc cùng một annotation có retention `RUNTIME` theo thiết kế.

Đừng chuyển tất cả annotation phục vụ processor sang `RUNTIME` chỉ vì có chữ “processor”. Hãy xem processor cần đọc nguồn, class file hay runtime reflection.

## 8. Công cụ đọc bytecode khác với reflection

Giả sử build pipeline có một công cụ kiểm tra rằng class được đánh dấu `@InternalApi` không được export trong thư viện. Công cụ chạy **sau `javac`** và chỉ nhận file `.class`. Một annotation loại này có thể khai báo:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.CLASS)
@Target(ElementType.TYPE)
@interface InternalApi {
    String owner();
}
```

Định nghĩa đó giữ metadata để một scanner hiểu được class-file format có thể đọc. `Class.getAnnotation(InternalApi.class)` khi chạy ứng dụng vẫn trả `null` cho annotation được giữ ở `CLASS`.

Nếu scanner là một **thư viện reflection** quét các class đã nạp, nó không hoạt động giống một bộ đọc bytecode. Khi đó, dù scanner được gọi “scan annotation”, chính sách `CLASS` là không đủ. Phải kiểm tra thư viện đang dùng `Class.getAnnotations()` hay đọc trực tiếp class bytes.

Một số công cụ bytecode có lựa chọn quét cả runtime-visible lẫn runtime-invisible annotations; việc `CLASS` có được tìm thấy phụ thuộc cấu hình và khả năng của công cụ. Lựa chọn retention đúng còn cần **kiểm chứng bộ scanner cụ thể** bằng một phép thử thực tế.

## 9. Framework runtime và việc xử lý annotation

Nhiều cơ chế runtime, chẳng hạn bộ định tuyến endpoint, đăng ký handler, kiểm tra method có annotation, hoặc bộ kiểm soát cấu hình, có thể đọc annotation qua reflection. Trong trường hợp đó, `RUNTIME` thường là yêu cầu.

Ví dụ:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Action {
    String value();
}
```

Một lớp có thể dùng:

```java
class InventoryService {
    @Action("reserve")
    void reserve() {
    }
}
```

Một thành phần runtime có thể lấy `InventoryService.class.getDeclaredMethod("reserve")` rồi gọi `getAnnotation(Action.class)` để tìm metadata. Đây mới là hành động **đọc metadata**; annotation không tự thực thi một method và không tự tạo cơ chế điều phối.

Một số framework còn khai thác bytecode, proxy, chỉ mục sinh sẵn hoặc các cách tối ưu khác. Vì vậy, với annotation của **framework có sẵn**, tuân theo retention mà framework/documentation yêu cầu; khi tự thiết kế annotation, quyết định dựa trên đường tiêu thụ metadata mà mình kiểm soát.

`@Retention(RUNTIME)` **không đảm bảo** framework sẽ tìm hoặc áp dụng annotation nếu framework không được lập trình nhận biết kiểu đó. Ngoài retention, vị trí gắn (`@Target`), phạm vi scan, khả năng truy cập method và cấu hình framework đều có thể quan trọng.

## 10. Các nhầm lẫn phổ biến khi chọn retention

### 10.1. Quên khai báo `@Retention` rồi chờ reflection

```java
@interface FeatureFlag {
    String name();
}

@FeatureFlag(name = "checkout")
class Checkout {}
```

Mặc định là `CLASS`. `Checkout.class.getAnnotation(FeatureFlag.class)` không trả được annotation này. Nếu runtime reflection là yêu cầu, khai báo thêm `@Retention(RetentionPolicy.RUNTIME)` **trên `FeatureFlag`** và biên dịch lại các mã sử dụng.

### 10.2. Dùng `SOURCE` cho scanner chỉ nhận `.class`

`SOURCE` không được lưu ở class file. Một bước hậu xử lý chỉ nhận `.jar` sẽ không thể đọc một annotation `SOURCE` được gắn trên class chỉ từ artifact ấy.

Nếu build tool cần metadata sau biên dịch, dùng `CLASS` hoặc `RUNTIME` phù hợp. Không thể khôi phục nội dung annotation `SOURCE` của một class đã biên dịch chỉ bằng việc đổi công cụ đọc.

### 10.3. Dùng `CLASS` cho `getAnnotation`

`CLASS` giữ dữ liệu ở classfile, **nhưng không dùng cho phản chiếu annotation tiêu chuẩn**. Hai dòng sau diễn đạt nhu cầu khác nhau:

```java
// Công cụ bytecode: đọc thuộc tính class file theo định dạng JVM.
// Java reflection:
SomeClass.class.getAnnotation(MyAnnotation.class);
```

Nếu đường xử lý thật sự là dòng thứ hai, chọn `RUNTIME`.

### 10.4. Nhầm `@Target` với `@Retention`

- `@Target(ElementType.METHOD)` trả lời “annotation đặt được ở đâu?”.
- `@Retention(RetentionPolicy.RUNTIME)` trả lời “annotation được giữ đến khi nào và khả kiến cho reflection hay không?”.

Một annotation có thể có `@Target(METHOD)` và `@Retention(SOURCE)` hoặc `@Retention(RUNTIME)` tùy bên đọc. Chọn target đúng không thay thế retention đúng.

### 10.5. Cho rằng `@Inherited` làm annotation kéo dài vòng đời

`@Inherited` liên quan cách một số annotation trên class được tìm thấy qua superclass; nó **không** biến `SOURCE` hoặc `CLASS` thành `RUNTIME`. Nếu muốn truy vấn annotation kế thừa bằng reflection, annotation vẫn cần retention thích hợp. Cơ chế `@Inherited` không tự áp dụng cho method, field, interface hay package như một quy tắc kế thừa tổng quát.

### 10.6. Dùng `@Documented` để giữ annotation lúc chạy

`@Documented` liên quan cách công cụ Javadoc đưa annotation vào tài liệu API. Nó không thay đổi retention policy. Tương tự, `@Repeatable` giải quyết việc cùng một annotation xuất hiện nhiều lần ở một vị trí hợp lệ; riêng meta-annotation này không làm một annotation `SOURCE` trở thành runtime-visible.

### 10.7. Chỉ sửa định nghĩa annotation nhưng không biên dịch lại mã đã chú thích

Nếu đổi `@Retention(SOURCE)` thành `@Retention(RUNTIME)`, các class **đã biên dịch theo bản cũ** không tự nhận metadata mới. Class file cũ có thể đã bỏ thông tin annotation; cần biên dịch lại **những nguồn có sử dụng annotation** và xây dựng artifact mới.

Ngay cả khi thay đổi từ `CLASS` sang `RUNTIME`, thuộc tính lưu annotation trong class file cũ chưa chắc phù hợp cơ chế reflection mới. Hãy rebuild toàn bộ phần mã bị ảnh hưởng trước khi đánh giá kết quả.

### 10.8. Dùng `RUNTIME` để sửa lỗi processor không chạy

Nếu processor chưa được cấu hình hoặc processor không hỗ trợ annotation, đổi retention sang `RUNTIME` **không xử lý được nguyên nhân**. Kiểm tra đăng ký processor, cấu hình `annotationProcessorPath`/build tool, hỗ trợ phiên bản Java và bộ lọc tên annotation.

Vấn đề “compiler có gọi processor không?” độc lập với vấn đề “annotation có tồn tại ở runtime không?”.

## 11. Tiêu chí thiết kế và đánh đổi

Một lựa chọn retention tốt cân bằng nhu cầu đọc với khả năng duy trì metadata.

### Giữ metadata đến mức cần thiết

Nếu annotation chỉ yêu cầu compiler cảnh báo lỗi, `SOURCE` đủ. Nếu cần phân tích bytecode sau biên dịch, tối thiểu phải giữ metadata (`CLASS` hoặc `RUNTIME`). Nếu reflection runtime là giao diện tiêu thụ, `RUNTIME` cần thiết.

Giữ metadata lâu hơn có thể làm class file hoặc artifact chứa thêm thông tin. Tuy nhiên, chỉ đổi retention không bảo đảm sẽ có cải thiện hiệu năng đáng kể; kích thước và chi phí phụ thuộc số lượng annotation, giá trị, class và cách framework scan. **Đừng đoán một con số hoặc tối ưu theo cảm giác**; hãy đo artifact và thời gian scan nếu đó thật sự là vấn đề.

### Bảo mật và dữ liệu nhạy cảm

Dù `SOURCE` không được ghi vào class file dưới dạng annotation, giá trị có thể còn trong mã nguồn, repository hoặc output của công cụ build. `CLASS` và `RUNTIME` khiến metadata hiện diện trong artifact. **Không đặt mật khẩu, token hoặc bí mật trực tiếp trong annotation values** với kỳ vọng `CLASS` khiến người dùng runtime không thể xem; công cụ đọc class file có thể trích xuất chúng.

### Phân biệt retention với sự hiện diện của annotation type

Class định nghĩa `MyAnnotation` có thể vẫn được biên dịch thành `MyAnnotation.class` và được tham chiếu bởi code bình thường, kể cả khi `@Retention(SOURCE)`. `SOURCE` loại bỏ **metadata của việc áp dụng annotation** khỏi class file được chú thích; nó không có nghĩa định nghĩa type nhất thiết biến mất khỏi toàn bộ chương trình.

Ví dụ trong mục 5, `SourceHint.class` vẫn được code reflection tham chiếu như một class literal, nhưng `OrderHandler.class` không mang annotation `@SourceHint` có thể đọc hoặc tìm từ bytecode.

### Tương thích và quy trình phát hành

Thay đổi retention là thay đổi hợp đồng tiêu thụ metadata. Nếu chuyển từ `RUNTIME` về `CLASS`, code trước đây gọi `getAnnotation` có thể ngừng tìm thấy metadata. Chuyển lên `RUNTIME` cần biên dịch lại các class có annotation và kiểm tra cả quy trình đóng gói, shading hoặc bytecode transformation. Khi API annotation đã được công bố cho nhiều module, cần thông báo và kiểm thử các consumer liên quan.

## 12. Quy trình lựa chọn trong dự án

Thực hiện tuần tự:

1. **Gọi tên metadata:** annotation dùng để mô tả điều gì, trên class/method/field/package hay vị trí khác? Chọn `@Target` riêng theo nhu cầu này.
2. **Xác định bên xử lý trực tiếp:** compiler, annotation processor, scanner classfile, hay Java reflection/framework?
3. **Xác định đầu vào của bên xử lý:** source code đang biên dịch, `.class` từ dependency, hay class đã nạp trong JVM?
4. **Chọn mức retention:**
   - Chỉ cần thông tin ở bước compiler đọc source: cân nhắc `SOURCE`.
   - Cần metadata trong class file cho bộ quét bytecode: cân nhắc `CLASS`.
   - Cần Java reflection lúc runtime: chọn `RUNTIME`.
5. **Đối chiếu công cụ thật:** bảo đảm processor được chạy, scanner đọc đúng attributes, hoặc framework có logic nhận annotation.
6. **Tạo một phép thử:** kiểm tra trực tiếp output của processor, `javap -v` trên class file, hoặc kết quả `getAnnotation`; đừng chỉ dựa vào việc source có `@Annotation`.
7. **Kiểm tra artifact sau đóng gói:** classfile metadata phải còn trong sản phẩm được sử dụng; một bước transform/obfuscation có thể tác động đến nó.

Ví dụ quyết định:

- “Dùng `@GenerateBuilder` để processor sinh mã khi `javac` đang biên dịch source”: `SOURCE` thường đủ.
- “Dùng `@ArchitectureRule` để plugin CI kiểm tra bytecode trong JAR”: `CLASS` thường đủ.
- “Dùng `@Route` để chương trình gọi `Method.getAnnotation(...)` lúc khởi động”: cần `RUNTIME`.

Nếu có hai bên xử lý khác nhau dùng **cùng một annotation type**, chọn chính sách đáp ứng bên cần metadata lâu nhất. Chẳng hạn, processor lúc biên dịch **và** reflection khi chạy cùng đọc một annotation thì chính sách phù hợp là `RUNTIME`.

## 13. Bài tập phân loại retention

Cho các tình huống:

1. Một annotation giúp compiler nhận diện chỗ cần bỏ qua cảnh báo, không công cụ nào xử lý metadata sau biên dịch.
2. Tool CI chỉ nhận file JAR sau build và quét các class chứa annotation để tạo báo cáo.
3. Ứng dụng dùng `Method.getDeclaredAnnotations()` để đăng ký các handler khi khởi động.
4. Processor sinh một class Java mới từ annotation trên source file đang biên dịch.
5. Công cụ chạy sau build quét file `.class`, còn ứng dụng cũng gọi `Class.getAnnotation(...)` để đọc chính annotation đó.
6. Một annotation không có `@Retention`: giá trị mặc định là gì?
7. Một class dùng annotation `SOURCE` được biên dịch xong: có thể lấy lại giá trị bằng `javap -v` trên class file được chú thích không?
8. Một annotation `CLASS` có còn trong bytecode không, và `Class.isAnnotationPresent(...)` có trả `true` không?

Đáp án:

1. **`SOURCE`**: phục vụ thời điểm biên dịch, không cần lưu class-file metadata.
2. **`CLASS`** thường đủ: tool đọc bytecode sau biên dịch; `RUNTIME` cũng lưu được nhưng không cần thiết nếu không có reflection.
3. **`RUNTIME`**: reflection cần runtime-visible annotations.
4. **`SOURCE`** thường đủ: processor xử lý source của lượt biên dịch hiện tại, nếu không có consumer sau đó.
5. **`RUNTIME`**: đáp ứng đồng thời bytecode scanner và reflection.
6. **`CLASS`**: đây là retention mặc định của Java.
7. **Không**: việc sử dụng annotation `SOURCE` không được lưu lại thành metadata trong class file được chú thích.
8. **Có trong class file, nhưng không xuất hiện qua reflection tiêu chuẩn**: `isAnnotationPresent(...)` trả `false` với annotation chỉ có `CLASS` nếu không có đường kế thừa/runtime annotation khác liên quan.

## 14. Checklist cuối bài

- Đã xác định **bên xử lý thật** thay vì dựa vào tên annotation hay tên framework.
- `@Target` mô tả đúng **vị trí áp dụng**, còn `@Retention` mô tả **vòng đời metadata**.
- Chỉ sử dụng trong lúc biên dịch nguồn → cân nhắc `SOURCE`.
- Cần đọc từ `.class`/`.jar` bằng scanner bytecode → `CLASS` thường đủ.
- Cần `Class`/`Method`/`Field.getAnnotation(...)` hoặc Java reflection → `RUNTIME`.
- Không có `@Retention` → Java mặc định `CLASS`.
- `CLASS` vẫn được lưu trong class file, dù Java reflection không thấy.
- `RUNTIME` không khiến annotation tự hoạt động; phải có code hoặc framework tiêu thụ nó.
- `@Documented` và `@Inherited` không thay thế retention.
- Khi thay retention, đã biên dịch lại các class có annotation và kiểm tra artifact thực tế.
- Đã xác nhận công cụ scanner/processor/framework đọc đúng kiểu annotation và đúng giai đoạn.
- Không đặt dữ liệu bí mật vào annotation values chỉ vì nghĩ metadata `CLASS` “ẩn” được khỏi ứng dụng.

Một annotation được định nghĩa tốt sẽ có retention thể hiện rõ **ai sẽ đọc**, **đọc từ dạng dữ liệu nào** và **đọc vào thời điểm nào**. Nhờ vậy metadata tồn tại đủ lâu cho consumer, đồng thời tránh kỳ vọng sai rằng compiler, bytecode tool và runtime reflection quan sát annotation theo cùng một cách.