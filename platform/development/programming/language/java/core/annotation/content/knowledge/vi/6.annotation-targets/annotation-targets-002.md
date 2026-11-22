# `ElementType.TYPE` và `ElementType.ANNOTATION_TYPE`: đích áp dụng trên lớp, giao diện, enum và kiểu annotation

## 1. Vấn đề cần hiểu: `@Target` kiểm soát vị trí gắn annotation

Khi **khai báo một loại annotation** bằng `@interface`, ta có thể dùng meta-annotation `java.lang.annotation.Target` để giới hạn **những vị trí cú pháp** được phép gắn annotation ấy. Mỗi lựa chọn được biểu diễn bởi một hằng trong enum `ElementType`.

Đối với các khai báo kiểu Java, hai hằng dễ bị nhầm là:

- **`ElementType.TYPE`**: annotation được phép gắn lên **khai báo kiểu**, bao gồm lớp (`class`), giao diện (`interface`), enum (`enum`), **kiểu annotation (`@interface`)** và record (`record`, từ Java 16).
- **`ElementType.ANNOTATION_TYPE`**: annotation chỉ được phép gắn lên **khai báo loại annotation** (`@interface`). Đây là đích chuyên biệt thường gặp ở các *meta-annotation*.

Ví dụ về khai báo hai loại annotation:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@interface TypeLabel {
    String value();
}

@Target(ElementType.ANNOTATION_TYPE)
@interface MetaLabel {
    String value();
}
```

Hai đoạn khai báo này chỉ định **nơi sử dụng hợp lệ** của `@TypeLabel` và `@MetaLabel`. Chúng chưa tạo ra xử lý runtime nào. `@Target` giúp trình biên dịch kiểm tra vị trí gắn; nội dung xử lý metadata, nếu cần, vẫn phải do compiler/processor hoặc mã thư viện thực hiện.

## 2. Bảng so sánh phạm vi

| Vị trí đặt annotation | `@Target(TYPE)` | `@Target(ANNOTATION_TYPE)` |
| --- | --- | --- |
| Trước khai báo `class Service {}` | Hợp lệ | Không hợp lệ |
| Trước khai báo `interface Repository {}` | Hợp lệ | Không hợp lệ |
| Trước khai báo `enum Status {}` | Hợp lệ | Không hợp lệ |
| Trước khai báo `@interface Audited {}` | **Hợp lệ** | **Hợp lệ** |
| Trước khai báo `record Point(int x, int y) {}` | Hợp lệ (Java 16+) | Không hợp lệ |
| Trước khai báo một phương thức | Không hợp lệ chỉ với `TYPE` | Không hợp lệ |
| Trước khai báo một trường | Không hợp lệ chỉ với `TYPE` | Không hợp lệ |

**Điểm quan trọng nhất:** `ANNOTATION_TYPE` là một đích **hẹp hơn** `TYPE`, xét các *khai báo*. Một loại annotation được đánh dấu `@Target(TYPE)` **được phép** gắn trên khai báo `@interface`; không cần thêm `ANNOTATION_TYPE` chỉ để đạt khả năng đó.

Ngược lại, một loại annotation có **duy nhất** `@Target(ANNOTATION_TYPE)` không được dùng trên lớp, giao diện hoặc enum thông thường. Ví dụ trong mã phía dưới sẽ kiểm chứng cả hai khả năng.

Bảng chỉ xét vị trí **khai báo**. Cú pháp sử dụng kiểu trong biểu thức, cast, generic type argument hoặc `implements` liên quan đến `TYPE_USE`, là khái niệm khác. `TYPE` không có nghĩa là “mọi nơi tên một kiểu xuất hiện”.

## 3. `TYPE`: đánh dấu một khai báo kiểu

Hãy định nghĩa `@TypeLabel` ở phần trên rồi dùng:

```java
@TypeLabel("class")
class PaymentService {}

@TypeLabel("interface")
interface PaymentGateway {}

@TypeLabel("enum")
enum PaymentStatus { NEW, PAID }

@TypeLabel("annotation")
@interface Logged {}

@TypeLabel("record")
record PaymentRequest(String id) {}
```

Tất cả vị trí gắn nêu trên đều phù hợp với `ElementType.TYPE` (với JDK hỗ trợ record). Trong đó:

- **Lớp**: `PaymentService` được khai báo bằng `class`.
- **Giao diện**: `PaymentGateway` được khai báo bằng `interface`.
- **Enum**: `PaymentStatus` được khai báo bằng `enum`. Gắn annotation vào **khai báo enum** khác với gắn lên **từng enum constant**.
- **Annotation type**: `Logged` là một loại annotation được khai báo bằng `@interface`; nó cũng thuộc nhóm khai báo kiểu, nên `TYPE` dùng được.
- **Record**: `PaymentRequest` là một loại record (Java 16+), cũng là đích hợp lệ của `TYPE`.

Những đoạn trên là **minh họa các vị trí khai báo**, cần ghép với định nghĩa `@TypeLabel` mới biên dịch. Ví dụ độc lập đầy đủ ở mục 5.

### Không nhầm khai báo enum với hằng enum

```java
// TYPE áp dụng cho khai báo enum:
@TypeLabel("payment-status")
enum Stage { NEW, DONE }
```

Nếu muốn gắn annotation lên từng `NEW` hoặc `DONE`, đó là vị trí khác (enum constant tương ứng với đích `FIELD`), không phải chính khai báo enum. Loại annotation chỉ có `@Target(TYPE)` không được gắn trực tiếp lên từng enum constant.

Tương tự, gắn annotation trước tên **khai báo class** không đồng nghĩa được gắn lên mọi field, constructor hoặc method *bên trong* class đó. Các vị trí ấy cần các đích thích hợp như `FIELD`, `CONSTRUCTOR` và `METHOD` nếu muốn hỗ trợ riêng.

## 4. `ANNOTATION_TYPE`: chỉ gắn lên khai báo loại annotation

Với khai báo:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.ANNOTATION_TYPE)
@interface MetaLabel {
    String value();
}
```

Nơi sử dụng **hợp lệ** là một khai báo `@interface`:

```java
@MetaLabel("used-for-auditing")
@interface Audited {}
```

Một số ví dụ **không hợp lệ**, dùng để nhận biết lỗi compiler (không đưa vào tệp của chương trình chạy):

```java
// KHÔNG HỢP LỆ: MetaLabel chỉ có ANNOTATION_TYPE.
@MetaLabel("service")
class OrderService {}

// KHÔNG HỢP LỆ: interface thường không phải @interface.
@MetaLabel("repository")
interface OrderRepository {}

// KHÔNG HỢP LỆ: enum thường không phải @interface.
@MetaLabel("status")
enum OrderStatus { OPEN, CLOSED }
```

Tên `MetaLabel` gợi ý cách dùng thường gặp: annotation **mô tả một loại annotation khác**. Đó chính là ý nghĩa của *meta-annotation*. Ví dụ các meta-annotation chuẩn như `@Target` và `@Retention` được thiết kế để áp dụng lên **khai báo loại annotation**.

Cần phân biệt ba tầng:

1. `@MetaLabel` được **khai báo** là một annotation type, có `@Target(ANNOTATION_TYPE)`.
2. `@MetaLabel("used-for-auditing")` được **sử dụng** trên khai báo `@interface Audited`.
3. `@Audited` (nếu sử dụng trên thành phần khác và được khai báo cho phép) là **một annotation riêng**; không mặc nhiên khiến thành phần ấy trực tiếp mang `@MetaLabel`.

Ví dụ, nếu một lớp có `@Audited`, thì `SomeClass.class.getAnnotation(MetaLabel.class)` **không tự động** tìm meta-annotation qua `@Audited`. Một framework muốn suy luận quan hệ meta-annotation phải chủ động tìm annotation type và kiểm tra metadata trên loại đó theo cơ chế của mình. Vì vậy, `@MetaLabel` không tự kích hoạt auditing chỉ vì được gắn lên `Audited`.

## 5. Ví dụ Java 17+ chạy độc lập: kiểm tra cả hai đích bằng Reflection

Tạo tệp **`TypeTargetsDemo.java`**. Tệp này gồm định nghĩa hai loại annotation, các vị trí gắn hợp lệ và mã đọc Reflection. Không cần Spring hoặc thư viện ngoài JDK.

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface TypeLabel {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.ANNOTATION_TYPE)
@interface MetaLabel {
    String value();
}

@TypeLabel("class")
class PaymentService {}

@TypeLabel("interface")
interface PaymentGateway {}

@TypeLabel("enum")
enum PaymentStatus { NEW, PAID }

@TypeLabel("annotation")
@MetaLabel("meta")
@interface Audited {}

@TypeLabel("record")
record PaymentRequest(String id) {}

public class TypeTargetsDemo {
    private static void inspect(Class<?> type) {
        TypeLabel typeLabel = type.getAnnotation(TypeLabel.class);
        MetaLabel metaLabel = type.getAnnotation(MetaLabel.class);

        String typeValue = typeLabel == null ? "-" : typeLabel.value();
        String metaValue = metaLabel == null ? "-" : metaLabel.value();

        System.out.println(type.getSimpleName()
                + " | TYPE=" + typeValue
                + " | ANNOTATION_TYPE=" + metaValue);
    }

    public static void main(String[] args) {
        inspect(PaymentService.class);
        inspect(PaymentGateway.class);
        inspect(PaymentStatus.class);
        inspect(Audited.class);
        inspect(PaymentRequest.class);
    }
}
```

Chạy trong thư mục chứa tệp:

```bash
javac -encoding UTF-8 TypeTargetsDemo.java
java TypeTargetsDemo
```

Kết quả stdout:

```text
PaymentService | TYPE=class | ANNOTATION_TYPE=-
PaymentGateway | TYPE=interface | ANNOTATION_TYPE=-
PaymentStatus | TYPE=enum | ANNOTATION_TYPE=-
Audited | TYPE=annotation | ANNOTATION_TYPE=meta
PaymentRequest | TYPE=record | ANNOTATION_TYPE=-
```

### Vì sao kết quả như vậy?

- `TypeLabel` được khai báo với `TYPE`, nên được gắn hợp lệ lên **cả năm** khai báo kiểu (class, interface, enum, annotation type và record).
- `MetaLabel` được khai báo với `ANNOTATION_TYPE`, nên trong chương trình chỉ xuất hiện hợp lệ trên **`@interface Audited`**.
- `@Retention(RUNTIME)` ở cả hai loại annotation khiến Reflection `getAnnotation(...)` có thể đọc metadata khi chạy. Không có `RUNTIME`, ví dụ vẫn có thể biên dịch nhưng cách truy xuất bằng Reflection thông thường sẽ không tìm được metadata.
- `Audited.class` là một đối tượng `Class` mô tả **loại annotation `Audited`**. `getAnnotation(MetaLabel.class)` ở đây đọc `@MetaLabel` trực tiếp trên **khai báo `Audited`**.
- Giá trị `"-"` trong bảng là chuỗi thay thế khi `getAnnotation(...)` trả về `null`; không phải giá trị do Java tự cung cấp.
- `inspect(...)` nhận một `Class<?>`, đọc metadata và in dòng mô tả. Không có logic framework đặc biệt; phần xử lý là mã Java trong chính chương trình.

Vì `TYPE` cho phép gắn lên `@interface`, dòng `Audited | TYPE=annotation` là bằng chứng thực hành rằng `TYPE` và `ANNOTATION_TYPE` **giao nhau tại khai báo loại annotation**.

### Thử thay đổi để thấy lỗi biên dịch

Giữ nguyên tệp mẫu, rồi **thử** thêm `@MetaLabel("wrong")` trước `class PaymentService`. `javac` sẽ từ chối vì `@MetaLabel` không áp dụng được cho loại khai báo đó. Sau khi thử, bỏ thay đổi này để chạy lại ví dụ hợp lệ.

Ngược lại, nếu chỉ bỏ `@MetaLabel("meta")` trước `@interface Audited`, chương trình vẫn biên dịch và chạy, nhưng dòng của `Audited` sẽ hiển thị `ANNOTATION_TYPE=-`. Điều này giúp phân biệt **khả năng gắn do `@Target` cho phép** với **việc đã thực sự gắn annotation tại vị trí cụ thể**.

## 6. Khác nhau giữa `TYPE`, `TYPE_USE` và `TYPE_PARAMETER`

Các tên hằng có chữ `TYPE` không mang nghĩa giống nhau:

| `ElementType` | Phạm vi chính | Ví dụ dễ hình dung |
| --- | --- | --- |
| `TYPE` | Khai báo class, interface, enum, annotation type, record | `@TypeLabel("x") class Service {}` |
| `ANNOTATION_TYPE` | Riêng khai báo `@interface` | `@MetaLabel("x") @interface Trace {}` |
| `TYPE_USE` | Các vị trí sử dụng kiểu theo quy tắc Java | `List<@NonNull String>` hoặc `(@NonNull String) obj` với loại annotation phù hợp |
| `TYPE_PARAMETER` | Vị trí khai báo type parameter | `class Box<@TypeParameterMarker T> {}` với loại annotation phù hợp |

Các ví dụ trong hai dòng cuối **chỉ minh họa vị trí** và cần khai báo annotation tương ứng mới biên dịch được. `TYPE_USE` liên quan đến **type contexts** và có một số chồng lấn với vị trí khai báo, nhưng không đồng nghĩa với `TYPE`. Cần đối chiếu chính xác `@Target` của annotation trước khi chọn vị trí gắn.

Ví dụ khác biệt cụ thể: nếu `@TypeLabel` chỉ có `@Target(TYPE)`, dùng nó trong `List<@TypeLabel("arg") String>` **không hợp lệ**, vì đây là vị trí *type argument*, cần hỗ trợ `TYPE_USE` thay vì chỉ `TYPE`.

Khi muốn một annotation áp dụng ở nhiều loại vị trí, có thể chỉ định **mảng đích**:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target({ElementType.TYPE, ElementType.METHOD})
@interface Marker {}
```

Lúc đó `@Marker` có thể gắn trên khai báo kiểu **hoặc** khai báo phương thức. Việc thêm nhiều đích là quyết định thiết kế API: chỉ nên cho phép các vị trí thực sự được consumer hỗ trợ. Thêm `ANNOTATION_TYPE` vào `{TYPE, ANNOTATION_TYPE}` thường không mở rộng tập khai báo vốn đã được `TYPE` bao phủ; nó chỉ có thể làm rõ ý định trong tài liệu/API.

## 7. `@Target` khác gì `@Retention`?

Đây là hai câu hỏi độc lập:

- **`@Target`**: “Annotation này được phép **gắn lên đâu**?” `TYPE`, `ANNOTATION_TYPE` là câu trả lời về *vị trí*.
- **`@Retention`**: “Annotation này được **lưu giữ đến giai đoạn nào**?” `SOURCE`, `CLASS`, `RUNTIME` là câu trả lời về *vòng đời metadata*.

Một annotation có `@Target(ANNOTATION_TYPE)` nhưng **không** có `@Retention(RUNTIME)` vẫn là meta-annotation hợp lệ về vị trí. Tuy nhiên, muốn đọc bằng `getAnnotation(...)` lúc chương trình chạy thì annotation đó phải được lưu với `RUNTIME`. Không thể suy retention từ target, hoặc suy target từ retention.

Khi **không khai báo `@Target`**, annotation có thể được sử dụng trên nhiều **vị trí khai báo** theo quy tắc mặc định của Java; không mặc nhiên mở rộng sang các vị trí type-use. Khi **không khai báo `@Retention`**, retention mặc định là `CLASS`. Hai giá trị mặc định phục vụ những mục đích khác nhau.

## 8. Một số tình huống thiết kế

### 8.1 Gắn nhãn cho tất cả kiểu nghiệp vụ

Bạn muốn người viết ứng dụng đánh dấu lớp xử lý, interface contract, enum trạng thái hoặc annotation type bằng cùng một nhãn khai báo. `@Target(TYPE)` có phạm vi đủ rộng. Bên xử lý có thể tự quyết định quét kiểu nào và phân biệt `Class.isInterface()`, `Class.isEnum()`, `Class.isAnnotation()` hoặc `Class.isRecord()`.

**Lưu ý:** target chỉ cho phép **gắn**. Không đảm bảo framework đã quét những kiểu đó hoặc tự tạo bean cho mọi lớp gắn annotation.

### 8.2 Thiết kế annotation để mô tả annotation khác

Bạn muốn định nghĩa `@BusinessQualifier` chỉ dành cho các annotation loại `@interface`. `@Target(ANNOTATION_TYPE)` diễn tả ranh giới chính xác: không thể vô tình gắn nó trực tiếp lên một class nghiệp vụ thông thường.

Nếu consumer cần tìm `@BusinessQualifier` thông qua một annotation khác, phải lập trình/thiết lập cơ chế truy tìm metadata trên loại annotation tương ứng. Java Reflection `getAnnotation` trên class không tự thực hiện tìm kiếm meta-annotation theo mọi tầng.

### 8.3 Kiểm soát vị trí gắn để tránh API gây hiểu lầm

Một annotation được dùng để điều khiển xử lý **chỉ dành cho class** nhưng lại đặt `@Target(TYPE)` sẽ có khả năng gắn cả trên interface, enum, annotation type và record. Nếu consumer thực sự chỉ xử lý class thông thường, cần quy định và kiểm tra thêm trong công cụ/processor hoặc mã runtime, thay vì hiểu nhầm rằng `TYPE` đồng nghĩa với `class` duy nhất.

`ElementType` cung cấp những **nhóm đích cú pháp**, không phải bộ lọc tất cả phân loại ngữ nghĩa (chẳng hạn “chỉ class không abstract”, “chỉ interface của module X”). Những quy tắc như vậy cần kiểm tra bổ sung.

## 9. Lỗi phổ biến và câu hỏi tự kiểm tra

**Lỗi 1: “`TYPE` nghĩa là chỉ class.”** Sai. `TYPE` bao gồm interface, enum, annotation type và record ở mức khai báo.

**Lỗi 2: “Muốn gắn annotation lên `@interface` thì bắt buộc phải có `ANNOTATION_TYPE`.”** Sai. `TYPE` cũng cho phép vị trí khai báo annotation type. `ANNOTATION_TYPE` hữu ích khi muốn **giới hạn chỉ còn** vị trí ấy.

**Lỗi 3: “Enum constant là một kiểu nên `TYPE` gắn được lên từng constant.”** Sai. Enum constant là một vị trí khác; thông thường cần đích `FIELD`.

**Lỗi 4: “`@Target(TYPE)` cũng cho phép đánh dấu type argument của `List<T>`.”** Sai. Type argument là vị trí type-use; cần hỗ trợ `TYPE_USE`.

**Lỗi 5: “Một meta-annotation trên `@interface Audited` sẽ tự động được Java áp dụng lên mọi class gắn `@Audited`.”** Sai. Annotation gắn trên một **loại annotation** và annotation gắn trên một **class** là những metadata trực tiếp khác nhau. Việc suy luận meta-annotation là công việc của consumer có hỗ trợ.

**Tự kiểm tra 1.** Cho `@Target(ElementType.ANNOTATION_TYPE) @interface OnlyMeta {}`. Có thể gắn `@OnlyMeta` lên `interface Gateway` không?

Đáp án: **Không**. Giao diện thường khai báo bằng `interface` không phải khai báo loại annotation bằng `@interface`.

**Tự kiểm tra 2.** Cho `@Target(ElementType.TYPE) @interface TypeTag {}`. Có thể dùng `@TypeTag @interface Marker {}` không?

Đáp án: **Có**. Khai báo `@interface` cũng là một khai báo kiểu, thuộc đích `TYPE`.

**Tự kiểm tra 3.** Vì sao `@MetaLabel("meta")` hiện ra trên `Audited.class` trong chương trình chạy?

Đáp án: nó được gắn **trực tiếp** lên khai báo `@interface Audited`; loại `MetaLabel` có `@Retention(RUNTIME)`, và mã Reflection gọi `getAnnotation(MetaLabel.class)` trên chính `Audited.class`.

**Tự kiểm tra 4.** Một annotation chỉ có `@Target(TYPE)` dùng được trên `@interface` nhưng không dùng được trên tham số phương thức. Điều gì kiểm soát khác biệt?

Đáp án: `@Target` xác định tập **vị trí đích** mà compiler cho phép. Tham số phương thức là `PARAMETER`, không thuộc `TYPE`.

**Tự kiểm tra 5.** Nếu một framework muốn quét duy nhất các lớp có `@TypeLabel`, có thể chỉ dựa vào `@Target(TYPE)` không?

Đáp án: **Không**. `TYPE` cũng hợp lệ trên interface, enum, record và annotation type. Framework cần kiểm tra loại khai báo và điều kiện của mình.

Khi chọn giữa `TYPE` và `ANNOTATION_TYPE`, hãy hỏi **annotation cần đánh dấu mọi khai báo kiểu hay chỉ chính các loại annotation?** Sau đó xác định rõ ai sẽ đọc metadata và vào thời điểm nào; `@Target` chỉ giải quyết tính hợp lệ của vị trí gắn.
