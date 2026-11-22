# @Retention và các chính sách RetentionPolicy trong Java

## 1. \`@Retention\` trả lời câu hỏi gì?

Khi khai báo một loại annotation trong Java, chúng ta có thể quyết định **metadata của loại annotation đó được giữ đến giai đoạn nào**. Meta-annotation \`java.lang.annotation.Retention\` cho phép đặt chính sách này:

```java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.RUNTIME)
@interface Audited {
    String value();
}
```

\`@Retention\` **gắn lên khai báo một loại annotation** (\`@interface Audited\`); đối số của nó là một hằng của enum \`RetentionPolicy\`.

Đừng nhầm hai thao tác:

- **Khai báo loại annotation**: \`@Retention(RetentionPolicy.RUNTIME) @interface Audited { ... }\` xác định vòng đời lưu giữ metadata của \`Audited\`.
- **Sử dụng annotation**: \`@Audited("payment") class PaymentService {}\` đặt metadata lên một khai báo cụ thể. Chính sách đã khai báo trên \`Audited\` quyết định metadata từ cách sử dụng này được đưa qua những giai đoạn nào.

Đây là chính sách về **lưu giữ annotation** khi biên dịch và chạy chương trình; nó **không nói rằng Java sẽ tự thực hiện hành vi nghiệp vụ**. Để có hành vi, phải có compiler, annotation processor, công cụ đọc bytecode, Reflection hoặc framework thực sự xử lý metadata.

## 2. Ba chính sách trong \`RetentionPolicy\`

Java định nghĩa ba giá trị chính:

| Chính sách | Hiện diện trong mã nguồn | Được ghi vào tệp \`.class\` | Đọc được bằng Reflection thông thường khi chạy? | Trường hợp sử dụng điển hình |
| --- | --- | --- | --- | --- |
| \`RetentionPolicy.SOURCE\` | Có | Không | Không | Thông tin chỉ cần khi phân tích/biên dịch mã nguồn |
| \`RetentionPolicy.CLASS\` | Có | Có | Không | Metadata cần giữ trong bytecode cho công cụ phân tích/biến đổi class |
| \`RetentionPolicy.RUNTIME\` | Có | Có | Có | Metadata mà mã Java hoặc framework cần đọc lúc chạy qua Reflection |

Nhớ ba mức theo thứ tự **SOURCE → CLASS → RUNTIME**, nghĩa là metadata tồn tại qua ngày càng nhiều giai đoạn:

```text
Mã nguồn .java
   │
   ├── @Retention(SOURCE) ──> compiler/processor có thể đọc ──> không lưu .class
   │
   ├── @Retention(CLASS)  ──> compiler/processor ──> lưu trong .class
   │                                               │
   │                                               └── công cụ đọc bytecode có thể xử lý
   │                                                   (Reflection thông thường không thấy)
   │
   └── @Retention(RUNTIME) ──> compiler/processor ──> lưu trong .class
                                                   │
                                                   └── runtime Reflection/framework đọc được
```

Đồ thị nói về **khả năng hiện diện**, không bảo đảm rằng có một công cụ/processor/framework nào được đăng ký để thực sự tiêu thụ annotation.

### \`SOURCE\`: chỉ cần ở giai đoạn mã nguồn

```java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.SOURCE)
@interface SourceHint {}
```

Khi một thành phần được gắn \`@SourceHint\`, trình biên dịch có thể xác nhận cú pháp và các quy tắc Java. Annotation processor hoạt động trong quá trình biên dịch cũng có thể đọc annotation từ mô hình chương trình.

Sau khi biên dịch, **cách sử dụng \`@SourceHint\` không được lưu trong \`.class\`**. Vì vậy, lúc chạy, \`getAnnotation(SourceHint.class)\` hoặc \`isAnnotationPresent(SourceHint.class)\` không tìm thấy thông tin đã gắn.

Ví dụ annotation chuẩn \`@Override\` có \`SOURCE\`: nó giúp compiler kiểm tra rằng phương thức thực sự ghi đè hoặc triển khai hợp lệ một phương thức ở supertype, nhưng ứng dụng không cần mang metadata này tới runtime để việc override hoạt động. \`@SuppressWarnings\` cũng là một ví dụ annotation chỉ cần ở phía compiler.

**Khi nào chọn?** Khi công dụng của annotation kết thúc ở lúc biên dịch và không cần lưu lại thông tin gắn annotation trong bytecode.

### \`CLASS\`: lưu trong bytecode, không mở cho Reflection thông thường

```java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.CLASS)
@interface BytecodeHint {}
```

\`CLASS\` nghĩa là **các cách sử dụng annotation được ghi vào tệp \`.class\`** để công cụ hiểu cấu trúc bytecode có thể phân tích. Chẳng hạn, một công cụ build/instrumentation đọc class file có thể kiểm tra metadata nếu công cụ ấy được thiết kế để làm như vậy.

Tuy nhiên, API Reflection thông thường như \`Class.getAnnotation(...)\`, \`Method.getDeclaredAnnotations()\` **không trả về các annotation có chính sách \`CLASS\`**. Việc có trong bytecode và việc Reflection hiển thị là hai điều khác nhau.

**Khi nào chọn?** Khi metadata cần tồn tại sau biên dịch nhưng người thiết kế không cần truy vấn nó bằng Reflection thông thường ở runtime. Một thư viện đọc class file có thể dùng metadata đó dù chương trình Java không nhìn thấy qua Reflection.

### \`RUNTIME\`: lưu trong bytecode và truy xuất lúc chạy

```java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.RUNTIME)
@interface RuntimeHint {
    String value();
}
```

Giả sử một class được gắn \`@RuntimeHint("customer")\`. Khi class được tải và mã gọi Reflection trên đúng thành phần, Java có thể trả về annotation ấy cùng giá trị \`"customer"\`.

**Khi nào chọn?** Khi logic chạy thực tế cần đọc metadata, ví dụ một framework tìm mapping, đăng ký test, cấu hình đối tượng hoặc áp dụng một quy tắc dựa trên annotation. \`RUNTIME\` chỉ làm metadata **khả dụng**; nó không tự gọi phương thức hoặc chạy framework.

## 3. Chính sách mặc định: không viết \`@Retention\` nghĩa là \`CLASS\`

Đây là một điểm thường gây lỗi:

```java
@interface DefaultHint {}
```

Khi loại annotation **không khai báo \`@Retention\`**, Java sử dụng mặc định **\`RetentionPolicy.CLASS\`**. Vì vậy:

- \`@DefaultHint\` vẫn là annotation hợp lệ.
- Metadata gắn bằng \`@DefaultHint\` được lưu trong class file.
- Reflection thông thường tại runtime **không đọc được** \`@DefaultHint\` chỉ vì annotation đã được lưu trong \`.class\`.

Nếu mục tiêu của bạn là \`SomeClass.class.getAnnotation(DefaultHint.class)\` trả về metadata, phải khai báo chính sách **\`RUNTIME\`** trên loại \`DefaultHint\`, rồi biên dịch lại mã liên quan. Việc đổi chính sách trên source mà vẫn chạy các \`.class\` cũ không bảo đảm dữ liệu bytecode đã được cập nhật.

**Đừng suy mặc định \`RUNTIME\` từ thực tế nhiều annotation trong framework được đọc lúc chạy.** Framework phải chủ động định nghĩa các annotation cần Reflection với retention thích hợp.

## 4. Ví dụ Java 17+ hoàn chỉnh: kiểm tra cả ba chính sách và mặc định

Tạo tệp **\`RetentionPoliciesDemo.java\`** chứa toàn bộ mã dưới đây. Chương trình dùng Java SE, không cần thư viện ngoài.

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
@interface SourceOnly {}

@Retention(RetentionPolicy.CLASS)
@Target(ElementType.TYPE)
@interface ClassOnly {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface RuntimeVisible {
    String value();
}

// Không có @Retention: chính sách mặc định là CLASS.
@Target(ElementType.TYPE)
@interface DefaultClassOnly {}

@SourceOnly
@ClassOnly
@RuntimeVisible("document-service")
@DefaultClassOnly
class DocumentService {}

public class RetentionPoliciesDemo {
    public static void main(String[] args) {
        Class<DocumentService> type = DocumentService.class;

        System.out.println("SOURCE: "
                + type.isAnnotationPresent(SourceOnly.class));
        System.out.println("CLASS: "
                + type.isAnnotationPresent(ClassOnly.class));
        System.out.println("DEFAULT: "
                + type.isAnnotationPresent(DefaultClassOnly.class));
        System.out.println("RUNTIME: "
                + type.isAnnotationPresent(RuntimeVisible.class));

        RuntimeVisible info =
                type.getDeclaredAnnotation(RuntimeVisible.class);
        System.out.println("RUNTIME value: " + info.value());
    }
}
```

Đặt terminal tại thư mục chứa file, rồi chạy:

```bash
javac -encoding UTF-8 RetentionPoliciesDemo.java
java RetentionPoliciesDemo
```

Kết quả **stdout chính xác**:

```text
SOURCE: false
CLASS: false
DEFAULT: false
RUNTIME: true
RUNTIME value: document-service
```

### Giải thích kết quả

1. \`SourceOnly\` có \`SOURCE\`. Metadata của \`@SourceOnly\` trên \`DocumentService\` chỉ phục vụ quá trình biên dịch; Reflection trả về \`false\`.
2. \`ClassOnly\` có \`CLASS\`. \`@ClassOnly\` được ghi trong bytecode nhưng Reflection thường không hiển thị; do đó \`false\`.
3. \`DefaultClassOnly\` không có \`@Retention\`, nên mặc định \`CLASS\`, và Reflection trả về \`false\`.
4. \`RuntimeVisible\` có \`RUNTIME\`. \`@RuntimeVisible("document-service")\` được lưu dưới dạng mà Reflection có thể đọc; \`isAnnotationPresent\` trả về \`true\`.
5. \`getDeclaredAnnotation(RuntimeVisible.class)\` đọc annotation gắn trực tiếp trên \`DocumentService\`, và \`info.value()\` trả về \`"document-service"\`.

Ví dụ đã biết trước \`DocumentService\` có annotation \`RuntimeVisible\`. Trong chương trình tổng quát, \`getDeclaredAnnotation\` **có thể trả \`null\`** nên cần kiểm tra trước khi gọi \`value()\`.

Hãy thử xóa \`@RuntimeVisible("document-service")\` khỏi \`DocumentService\`: chương trình vẫn biên dịch nhưng \`getDeclaredAnnotation\` trả \`null\`; đoạn code mẫu sẽ ném \`NullPointerException\` ở \`info.value()\`. Tình huống này chỉ ra rằng \`RUNTIME\` **cho phép truy vấn**, nhưng không bảo đảm mỗi thành phần đều mang annotation ấy.

### Xem metadata trong bytecode với \`javap\`

Với bộ JDK, có thể kiểm tra nội dung \`.class\` sau khi biên dịch:

```bash
javap -v DocumentService
```

Trong phần thông tin annotation của kết quả \`javap -v\`, bạn có thể nhận biết hai nhóm:

- **\`RuntimeVisibleAnnotations\`**: biểu diễn các annotation được lưu với chính sách \`RUNTIME\`, ví dụ \`RuntimeVisible\`.
- **\`RuntimeInvisibleAnnotations\`**: có thể thấy các annotation được lưu với \`CLASS\`, ví dụ \`ClassOnly\` và \`DefaultClassOnly\`.
- Cách sử dụng **\`SourceOnly\`** không được phát ra trong class file do \`SOURCE\`, nên không nằm trong các annotation của \`DocumentService.class\`.

Đừng phụ thuộc vào thứ tự hay offset trong toàn bộ output \`javap -v\`; nội dung chi tiết gồm constant pool và thông tin compiler có thể khác. Ở đây, thông tin cần đối chiếu là **tồn tại trong bytecode** và **khả năng truy xuất bằng Reflection**. Chúng là hai trục không đồng nghĩa.

## 5. \`@Retention\` được đặt ở đâu, và khác \`@Target\` thế nào?

\`@Retention\` là **meta-annotation**: nó mô tả **một loại annotation**, được đặt trên khai báo \`@interface\`:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface TrackedAction {
    String value();
}

class PaymentService {
    @TrackedAction("PAYMENT")
    public void pay() {}
}
```

Phân biệt rõ:

| Thành phần | Câu hỏi được trả lời | Trong ví dụ |
| --- | --- | --- |
| \`@Retention(RUNTIME)\` trên \`TrackedAction\` | **Bao lâu** metadata được lưu giữ? | Đến lúc chạy, đọc bằng Reflection được |
| \`@Target(METHOD)\` trên \`TrackedAction\` | Annotation được gắn **ở đâu**? | Trên khai báo phương thức |
| \`@TrackedAction("PAYMENT")\` trên \`pay()\` | Thành phần này mang **giá trị metadata nào**? | \`value = "PAYMENT"\` |
| Consumer của \`TrackedAction\` | **Ai** đọc và **làm gì** với metadata? | Phải được viết hoặc cấu hình riêng |

Một annotation \`@Target(METHOD)\` vẫn có thể là \`SOURCE\`, \`CLASS\` hoặc \`RUNTIME\`. Ngược lại, \`@Retention(RUNTIME)\` không cho phép annotation gắn ở mọi vị trí; \`@Target\` và các quy tắc Java vẫn kiểm soát nơi dùng.

Đoạn code này chỉ là minh họa về cách khai báo/sử dụng; nó không có \`main\` hoặc consumer. Nếu chỉ biên dịch và gọi \`pay()\`, việc có \`@TrackedAction\` **không tự in log, không tự tạo giao dịch**.

Nếu cần dùng \`getDeclaredAnnotation(TrackedAction.class)\`, hãy lấy đối tượng \`Method\` tương ứng với \`pay\`, vì annotation được gắn trên **phương thức**, không phải trên chính \`PaymentService.class\`.

## 6. Quy trình xử lý tại compile-time và runtime

\`RetentionPolicy\` nói về khả năng tồn tại của metadata. Bên xử lý và thời điểm xử lý vẫn phải được xác định riêng:

### Compiler và annotation processor

Khi biên dịch mã Java, compiler kiểm tra annotation theo quy tắc ngôn ngữ: tên loại, các phần tử, kiểu giá trị, vị trí \`@Target\`, và những ràng buộc khác.

Một **annotation processor** được đăng ký trong pipeline biên dịch có thể đọc metadata trên các phần tử chương trình bằng API \`javax.annotation.processing\` và \`javax.lang.model\`. Processor có thể báo lỗi/warning hoặc sinh tệp. Nó không bắt buộc annotation phải có \`RUNTIME\` mới đọc được ở compile-time.

Do đó:

- \`SOURCE\` thích hợp nếu chỉ processor/compiler cần metadata trong quá trình biên dịch.
- \`CLASS\` và \`RUNTIME\` cũng có thể được processor thấy khi biên dịch.
- Chỉ viết \`@Retention(SOURCE)\` **không tự khởi chạy processor**. Phải có processor tương ứng được cung cấp và kích hoạt qua cấu hình compiler/build.

### Công cụ đọc bytecode

Một công cụ đọc \`.class\` có thể quan sát metadata \`CLASS\` hoặc \`RUNTIME\` khi nó hỗ trợ các thuộc tính class file liên quan. Ví dụ này độc lập với Reflection và không đòi hỏi chương trình nghiệp vụ phải đang chạy.

Nếu một thư viện dùng một trình đọc class file riêng, đừng vội kết luận rằng annotation nó tiêu thụ phải có \`RUNTIME\`. Cần xem **API đọc metadata cụ thể** của thư viện ấy.

### Reflection và framework tại runtime

Các API Reflection thông thường như \`Class.getDeclaredAnnotation\`, \`Method.getAnnotation\`, \`Field.getDeclaredAnnotations\` chỉ cung cấp annotation thích hợp có retention \`RUNTIME\`. Framework sử dụng Reflection thường cần chính sách đó cho annotation mà nó truy vấn.

Một framework cũng có thể có cơ chế đọc metadata khác, cache khi khởi động hoặc tạo mã lúc build. Vì vậy, cách kiểm chứng đúng là **xác định consumer và cơ chế truy xuất**, rồi chọn retention phù hợp.

Retention \`RUNTIME\` chỉ là điều kiện để annotation nhìn thấy bằng Reflection; **nó không tự phát hiện, tự gọi hoặc tự áp dụng logic**. Chẳng hạn, việc đặt \`@Transactional\` của Spring lên một phương thức không khiến Java SE tự quản lý transaction. Spring phải có hạ tầng và đường gọi hỗ trợ phù hợp.

## 7. Những trường hợp dễ nhầm

### 7.1 “\`CLASS\` nghĩa là chỉ tồn tại trong source?”

Không. \`CLASS\` **tồn tại trong file \`.class\`** sau khi biên dịch. Khác biệt là Reflection thông thường không hiển thị nó. Dùng \`javap -v\` hoặc công cụ đọc bytecode là cách quan sát phù hợp.

### 7.2 “\`RUNTIME\` làm annotation tự thực thi?”

Không. \`@Retention(RUNTIME)\` chỉ giữ metadata để runtime có thể đọc. Khi không có consumer, sự hiện diện của metadata không tự tạo ra log, mapping, quyền truy cập hay transaction.

### 7.3 “Annotation không khai báo \`@Retention\` sẽ có \`RUNTIME\`?”

Không. Giá trị mặc định của retention là **\`CLASS\`**. Đây là lý do phổ biến khiến annotation tự viết gắn đúng nhưng \`getAnnotation(...)\` trả \`null\`.

### 7.4 “Nếu \`RUNTIME\`, dùng \`getAnnotation\` trên đối tượng nào cũng được?”

Không. Bạn phải đọc **đúng loại thành phần mang annotation**. Chẳng hạn, annotation nằm trên method phải được đọc từ \`Method\`, annotation nằm trên field phải đọc từ \`Field\`. Các cơ chế kế thừa annotation như \`@Inherited\` có quy tắc riêng; chúng không biến mọi annotation phương thức hoặc interface thành metadata được kế thừa tự động.

### 7.5 “Giữ annotation đến runtime nghĩa là metadata có thể thay đổi như field?”

Không. Giá trị phần tử annotation được khai báo theo các quy tắc hằng tại compile-time. Retention \`RUNTIME\` không biến nó thành một trạng thái mutable hoặc tham số nhận từ request lúc chạy. Nếu một giá trị phải thay đổi theo môi trường, cần thiết kế cấu hình hoặc dữ liệu runtime tương ứng.

### 7.6 “\`@Retention\` là cách khai báo vị trí áp dụng?”

Không. Vị trí do \`@Target\` xác định. Ví dụ annotation chỉ được gắn lên \`METHOD\` vẫn phải chọn riêng retention tương ứng với bên tiêu thụ.

### 7.7 “Có \`RUNTIME\` thì mọi annotation khác gắn trên annotation đó tự chuyển sang class được gắn?”

Không. Nếu \`@MyStereotype\` được gắn lên một class và bản thân khai báo \`MyStereotype\` có các meta-annotation khác, Reflection thuần trên class **không tự truy duyệt toàn bộ các meta-annotation theo mọi tầng**. Consumer muốn suy luận như vậy phải có logic riêng. Retention chỉ đảm bảo annotation tương ứng có thể đọc được ở vị trí metadata thực sự được lưu.

## 8. Chọn chính sách nào khi tự thiết kế annotation?

Bắt đầu bằng một câu hỏi: **bên nào cần đọc annotation, vào thời điểm nào?**

| Nhu cầu thực tế | Chính sách có thể phù hợp | Vì sao |
| --- | --- | --- |
| Compiler/annotation processor kiểm tra quy ước khi build, xong rồi bỏ | \`SOURCE\` | Không cần đưa metadata vào class file |
| Công cụ đọc hoặc biến đổi \`.class\` cần metadata nhưng Reflection không cần | \`CLASS\` | Metadata còn trong bytecode |
| Java Reflection trong ứng dụng cần đọc annotation lúc chạy | \`RUNTIME\` | Runtime API có thể truy xuất |
| Chưa xác định consumer hoặc cơ chế xử lý | Chưa thể chọn theo hành vi mong muốn | Cần làm rõ ai sẽ đọc metadata trước |

Ví dụ, một annotation \`@GenerateMapper\` chỉ được một annotation processor sử dụng khi biên dịch có thể dùng \`SOURCE\`. Một annotation \`@Route\` mà framework tự viết đọc bằng \`getDeclaredAnnotation\` ở runtime phải có \`RUNTIME\`.

**Lưu ý:** không có lý do chọn \`RUNTIME\` cho tất cả annotation chỉ để “phòng khi cần”. Nó khiến metadata tồn tại thêm trong class file và khả dụng qua runtime Reflection; hãy chọn đúng mục đích. Tuy nhiên, nếu thư viện/framework bạn đang dùng đã quy định một chính sách riêng, hãy tuân theo hợp đồng của nó.

## 9. Bài tập kiểm tra kiến thức

**Bài 1.** Định nghĩa \`@interface Label {}\` và gắn \`@Label\` lên \`class A {}\`. Sau khi biên dịch, \`A.class.isAnnotationPresent(Label.class)\` trả về gì?

**Đáp án:** \`false\`, vì không có \`@Retention\` thì chính sách mặc định là \`CLASS\`, không được truy xuất qua Reflection thông thường.

**Bài 2.** Một annotation dùng \`SOURCE\` có thể được một annotation processor phát hiện khi biên dịch không?

**Đáp án:** Có, miễn processor được đăng ký/chạy và truy xuất vị trí chứa annotation thích hợp. \`SOURCE\` chỉ nói metadata không còn trong bytecode sau biên dịch.

**Bài 3.** \`javap -v\` hiển thị metadata của một annotation trong \`RuntimeInvisibleAnnotations\`. Từ đó có thể suy ra \`Class.getAnnotation(...)\` sẽ đọc được annotation ấy không?

**Đáp án:** Không. Metadata được ghi trong \`.class\` nhưng nhóm \`RuntimeInvisibleAnnotations\` không được Reflection thông thường công bố.

**Bài 4.** Thay \`@Retention(CLASS)\` bằng \`@Retention(RUNTIME)\` trên một annotation tự viết có khiến phương thức gắn annotation tự chạy không?

**Đáp án:** Không. Chỉ thay đổi vòng đời metadata; phải có consumer và một luồng thực thi để tạo hành vi.

**Bài 5.** Một loại annotation có \`@Retention(RUNTIME)\` và \`@Target(METHOD)\`. \`MyClass.class.getAnnotation(MyAnnotation.class)\` có phải là cách đúng để kiểm tra annotation được gắn lên \`doWork()\`?

**Đáp án:** Không. Phải tìm đối tượng \`Method\` mô tả \`doWork()\` rồi dùng \`method.getAnnotation(MyAnnotation.class)\` hoặc API tương ứng.

**Bài 6.** Nếu một công cụ build đọc trực tiếp \`.class\`, chính sách tối thiểu phù hợp để giữ metadata tới bytecode là gì?

**Đáp án:** \`CLASS\`. \`RUNTIME\` cũng lưu trong bytecode nhưng cần thiết khi Reflection runtime phải thấy metadata; lựa chọn chính xác còn tùy yêu cầu consumer.

\`@Retention\` quyết định **annotation được lưu đến khi nào**, chứ không xác định nơi gắn hay hành vi nghiệp vụ. \`SOURCE\` phục vụ xử lý từ source, \`CLASS\` còn trong bytecode, \`RUNTIME\` còn trong bytecode **và** đọc được bằng Reflection thông thường; nếu bỏ qua \`@Retention\`, mặc định là \`CLASS\`.
