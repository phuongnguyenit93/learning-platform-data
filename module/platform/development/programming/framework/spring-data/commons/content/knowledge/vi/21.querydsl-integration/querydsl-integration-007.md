# Đối chiếu phiên bản Querydsl cùng nhánh thư viện tương thích

Tích hợp Querydsl với Spring Data không chỉ là chọn một số phiên bản rồi thêm dependency. Một cấu hình hoạt động cần đồng thời phù hợp với release train Spring Data, module lưu trữ, nhánh phân phối Querydsl, namespace persistence, annotation processor và JDK của dự án.

Hai dependency có cùng tên artifact hoặc cùng số phiên bản chưa đủ để kết luận tương thích. Ngược lại, việc import Java vẫn bắt đầu bằng `com.querydsl` cũng không chứng minh JAR đến từ cùng một nhánh phân phối.

Bài học này hướng dẫn lập ma trận tương thích và nhận diện các điểm lệch giữa lúc sinh Q-type, biên dịch và chạy repository. Các ký hiệu phiên bản trong ví dụ là chỗ cần điền từ bộ dependency đã được xác minh, không phải khuyến nghị một phiên bản mới nhất dùng chung cho mọi dự án.

## 1. Mục tiêu và phạm vi

Sau bài này, bạn có thể:

- Phân biệt phiên bản Spring Data với phiên bản Querydsl.
- Nhận diện nhánh artifact gốc và nhánh fork qua tọa độ dependency.
- Đối chiếu namespace `javax.persistence` và `jakarta.persistence` trong tích hợp JPA.
- Đồng bộ core, adapter và annotation processor theo bộ phát hành phù hợp.
- Giải thích vì sao build thành công trên IDE chưa chứng minh runtime và CI dùng cùng bộ thư viện.
- Chọn đúng bằng chứng khi xử lý lỗi thiếu Q-type, thiếu lớp hoặc sai chữ ký phương thức.

Phạm vi dùng chung thuộc Spring Data Commons gồm các abstraction như `QuerydslPredicateExecutor`, predicate và cơ chế repository. Việc thực thi Querydsl do module lưu trữ hỗ trợ; không suy ra mọi module Spring Data đều có cùng khả năng tích hợp.

Phần namespace EntityManager và classifier JPA trong bài chỉ áp dụng cho tích hợp JPA. Querydsl SQL hay một adapter cho loại kho khác cần đối chiếu chính bộ artifact của nó.

## 2. Những phiên bản nào phải được đối chiếu?

Một dự án có thể chứa nhiều hệ phiên bản độc lập:

| Thành phần | Cần xác định điều gì? | Vì sao liên quan? |
| --- | --- | --- |
| Spring Boot, nếu có | Phiên bản và dependency management được áp dụng | Có thể quản lý phiên bản Spring Data cùng các dependency khác |
| Spring Data release train | Bộ phát hành mà dự án chọn | Giữ các module Spring Data trong bộ tương thích |
| Spring Data Commons | Phiên bản thực tế được resolve | Cung cấp hợp đồng repository và tích hợp chung |
| Module lưu trữ | Ví dụ module JPA hoặc module khác đang dùng | Cung cấp implementation và phạm vi hỗ trợ Querydsl |
| Querydsl | Group, artifact, version và classifier | Xác định đúng thư viện biểu thức và adapter |
| Annotation processor | Nhánh, phiên bản và cấu hình processor path | Sinh Q-type từ domain |
| Persistence API và provider | Namespace cùng phiên bản thích hợp | Quyết định kiểu EntityManager và annotation được dùng |
| JDK và build tool | Phiên bản dùng ở máy lập trình và CI | Ảnh hưởng biên dịch và annotation processing |

Không chọn Querydsl bằng cách lấy cùng số major với Spring Data. Các dự án có chu kỳ phát hành và cách đánh số riêng.

Nếu dùng Spring Boot, bắt đầu từ dependency management cùng tài liệu của phiên bản Boot đang sử dụng. Không mặc định BOM quản lý mọi artifact của mọi fork hoặc mọi dependency trên processor path.

Nếu không dùng Boot, vẫn cần một bộ phiên bản Spring Data nhất quán theo cơ chế quản lý dependency phù hợp. Tránh tự chọn từng module Spring Data chỉ theo tiêu chí mỗi module đều có một bản phát hành mới.

## 3. Phân biệt nhánh artifact và package Java

### 3.1. Tọa độ dependency xác định nguồn phân phối

Hai họ tọa độ cần nhận diện trong hệ sinh thái Querydsl:

| Họ phân phối | Group thường gặp | Artifact minh họa |
| --- | --- | --- |
| Querydsl gốc | `com.querydsl` | `querydsl-core`, `querydsl-jpa`, `querydsl-apt` |
| Fork OpenFeign Querydsl | `io.github.openfeign.querydsl` | Các artifact Querydsl tương ứng được nhánh đó phát hành |

Việc một release Spring Data hỗ trợ hoặc kiểm thử với họ nào, ở mức nào, phải được đối chiếu với tài liệu và release note của chính release đó. Không suy từ việc một fork tồn tại thành việc mọi phiên bản Spring Data đều hỗ trợ toàn bộ tính năng của fork.

Cũng không so sánh số phiên bản của hai nhánh như thể chúng cùng một trục phát hành. Số lớn hơn ở một nhánh không tự chứng minh nó thay thế trực tiếp mọi bản của nhánh khác.

### 3.2. Group khác không có nghĩa package Java khác

Fork có thể giữ các package Java tương thích như:

```java
import com.querydsl.core.types.Predicate;
import com.querydsl.core.types.dsl.BooleanExpression;
```

Vì vậy, đổi group dependency sang `io.github.openfeign.querydsl` không đồng nghĩa phải đổi import thành một package Java cùng tên group mới.

Package và chữ ký API phải được xác định từ thư viện thực tế. Một tên lớp giữ nguyên chỉ cho thấy cùng định danh lớp; nó chưa chứng minh mọi constructor, phương thức và hành vi đều giống nhau.

### 3.3. Trộn hai nhánh có thể gây trùng lớp

Xét một đồ thị dependency có:

```text
com.querydsl:querydsl-core:VERSION_A
io.github.openfeign.querydsl:querydsl-core:VERSION_B
```

Hai tọa độ khác group nên công cụ quản lý dependency không mặc nhiên xem chúng là hai phiên bản của cùng một module để chọn một và loại một.

Nếu cả hai JAR chứa cùng tên lớp đầy đủ, classpath có thể bị trùng lớp. Tùy cách đóng gói và nạp lớp, ứng dụng có thể dùng một lớp khác với lớp được kỳ vọng.

Hệ quả có thể là lỗi biên dịch, cảnh báo trùng lớp hoặc lỗi liên kết lúc chạy như `NoSuchMethodError`. Không dựa vào thứ tự classpath để làm cấu hình “tạm chạy được”.

Nguyên tắc là chọn một họ Querydsl phù hợp cho bộ tích hợp, rồi kiểm soát các dependency bắc cầu đưa họ còn lại vào. Một ngoại lệ kết hợp chỉ nên dựa trên tương thích được xác nhận rõ, không dựa vào việc ứng dụng đã khởi động một lần.

## 4. Namespace JPA là một trục tương thích riêng

### 4.1. javax.persistence và jakarta.persistence là hai kiểu khác nhau

Hai import sau không biểu diễn cùng một kiểu Java:

```java
import javax.persistence.EntityManager;
```

```java
import jakarta.persistence.EntityManager;
```

Một API Querydsl JPA được biên dịch với EntityManager thuộc namespace này không tự nhận EntityManager thuộc namespace còn lại chỉ vì tên ngắn giống nhau.

Cần đối chiếu đồng thời:

- Annotation entity, chẳng hạn `Entity` và `Id`.
- Persistence API trên compile classpath.
- Provider JPA và tích hợp của module Spring Data JPA.
- Biến thể `querydsl-jpa` đang được dùng.
- Annotation processor nhận diện annotation entity tương ứng.

Không chữa lỗi namespace bằng cách thêm cả hai persistence API vào classpath rồi coi đó là đã chuyển đổi tương thích. Làm vậy có thể che bớt lỗi thiếu lớp nhưng vẫn giữ hai hệ kiểu không tương thích.

### 4.2. Classifier hoặc cách đóng gói phụ thuộc nhánh và phiên bản

Một số bản phân phối Querydsl cung cấp biến thể Jakarta qua classifier. Ví dụ tọa độ có dạng:

```text
com.querydsl:querydsl-jpa:Q_VERSION:jakarta
com.querydsl:querydsl-apt:Q_VERSION:jakarta
```

Đây là mẫu dành cho các bản thực sự công bố biến thể đó. Cần kiểm tra artifact và classifier của phiên bản được chọn; không sao chép quy ước classifier từ nhánh này sang mọi phiên bản hoặc mọi fork.

Tương tự, không gắn classifier `jakarta` cho mọi artifact một cách máy móc. Core biểu thức và adapter JPA có vai trò khác nhau, và danh sách biến thể được công bố phải được xem theo từng artifact.

Ma trận đối chiếu nên thể hiện:

| Domain và provider | Adapter cần khớp | Processor cần khớp |
| --- | --- | --- |
| Hệ JPA dùng javax.persistence | Biến thể nhận kiểu JPA javax | Biến thể nhận diện annotation javax tương ứng |
| Hệ JPA dùng jakarta.persistence | Biến thể nhận kiểu JPA jakarta | Biến thể nhận diện annotation jakarta tương ứng |
| Tích hợp không dùng JPA | Adapter của loại kho đang dùng | Cơ chế sinh mã phù hợp, nếu cần |

Các hàng trên mô tả điều kiện tương thích, không gán một số phiên bản cố định cho mọi dự án.

## 5. Annotation processor phải đi cùng bộ thư viện đã chọn

Q-type như `QCustomer` thường được sinh trong bước annotation processing. Đây là một lớp tương thích riêng, không chỉ là chuyện có dependency runtime.

Có ít nhất ba tập thành phần cần phân biệt:

| Tập thành phần | Vai trò |
| --- | --- |
| Application compile classpath | Biên dịch domain, repository và mã dùng Q-type |
| Annotation processor path | Nạp processor cùng dependency để sinh mã |
| Runtime classpath | Chạy ứng dụng và implementation truy vấn |

Ba tập này có thể được resolve riêng. Việc ứng dụng có đúng persistence API trên compile classpath chưa bảo đảm processor nhìn thấy API đó.

Cần xác định:

1. Processor thuộc họ Querydsl nào.
2. Phiên bản processor có phù hợp với bộ core và adapter không.
3. Processor nhận diện annotation domain thuộc namespace nào.
4. Processor có đủ dependency cần cho chính nó trên processor path.
5. Thư mục generated sources có được đưa vào source set biên dịch không.

### 5.1. Không dựa vào việc processor luôn tự được phát hiện

Cách kích hoạt annotation processing phụ thuộc JDK, build tool và plugin biên dịch. Cần cấu hình processor path hoặc cơ chế tương ứng rõ ràng theo bộ công cụ đang dùng.

IDE có thể tự chạy một processor hoặc giữ Q-type từ lần build trước. Vì vậy, việc IDE không báo lỗi chưa chứng minh một môi trường CI sạch sẽ sinh được mã.

Một build sạch có giá trị khi nó tái tạo Q-type từ source và cấu hình đã khai báo, thay vì vô tình dùng lại output cũ.

### 5.2. Q-type cũ có thể che lệch phiên bản

Sau khi đổi nhánh, namespace hoặc phiên bản liên quan đến sinh mã, cần tạo lại Q-type bằng bộ processor đã chọn.

Không sửa tay hàng loạt Q-type để làm chúng có vẻ khớp với dependency mới. Lần sinh tiếp theo sẽ ghi đè thay đổi, còn cấu hình sai vẫn tồn tại.

Generated source là đầu ra của một quy trình. Muốn kết quả ổn định, phải giữ được đầu vào, processor và phiên bản của quy trình đó.

### 5.3. Annotation Generated không đủ để nhận diện namespace JPA

Có thể thấy trong mã sinh:

```java
import javax.annotation.processing.Generated;
```

Đây là annotation thuộc API xử lý annotation của JDK, không phải Entity hoặc EntityManager của JPA. Sự xuất hiện của tên `javax` ở đây không tự chứng minh dự án Jakarta đang dùng sai biến thể JPA.

Hãy kiểm tra đúng các kiểu persistence liên quan. Không thay tất cả import bắt đầu bằng `javax` thành `jakarta`; nhiều package có lịch sử và vai trò khác nhau.

## 6. Lập một ma trận tương thích có bằng chứng

Thay vì ghi một dòng “Querydsl phiên bản X tương thích”, hãy lập bảng đủ ngữ cảnh:

| Trục đối chiếu | Giá trị cần ghi | Bằng chứng cần có |
| --- | --- | --- |
| Nền tảng | Boot hoặc cơ chế quản lý dependency khác | Parent/BOM và effective dependency management |
| Spring Data | Release train, Commons và module cụ thể | Phiên bản thực tế đã resolve |
| Phạm vi hỗ trợ | Module hỗ trợ kiểu tích hợp nào | Tài liệu và release note đúng phiên bản |
| Họ Querydsl | Group artifact đã chọn | Tọa độ đầy đủ trong dependency graph |
| Bộ Querydsl | Core, adapter và processor | Version cùng classifier được resolve ở từng classpath |
| Namespace JPA | javax hoặc jakarta, nếu dùng JPA | Import domain, API và provider thực tế |
| JDK/build | JDK, toolchain và plugin biên dịch | Cấu hình dùng ở build chính thức và CI |
| Q-type | Cách sinh và đưa vào biên dịch | Generated source được tạo từ một build sạch |
| Runtime | Bộ JAR được đóng gói | Nội dung dependency runtime và kết quả chạy tối thiểu |

Với một thành phần chưa có bằng chứng, ghi rõ chưa xác định thay vì điền theo suy đoán từ tên framework.

### 6.1. Thứ tự đối chiếu tài liệu

Một quy trình hợp lý:

1. Xác định release nền tảng và module đang sử dụng.
2. Đọc tài liệu hoặc release note của đúng release đó để nhận diện phạm vi hỗ trợ Querydsl.
3. Đối chiếu tài liệu của nhánh Querydsl tương ứng về JDK, adapter, classifier và processor.
4. Kiểm tra BOM hoặc dependency management có thực sự quản lý các tọa độ đang khai báo.
5. Đối chiếu với dependency graph đã resolve và classpath thực tế.

Tài liệu đang hiển thị mặc định phiên bản mới nhất có thể mô tả một bộ khác với dự án. Lưu lại phiên bản tài liệu hoặc release tương ứng khi ghi nhận quyết định kỹ thuật.

Một ví dụ từ dự án khác chỉ là gợi ý tìm hiểu. Nếu khác release train, namespace hoặc nhánh Querydsl, ví dụ đó chưa phải bằng chứng tương thích.

### 6.2. Tọa độ đầy đủ quan trọng hơn số phiên bản đứng riêng

Ghi đủ các thành phần:

```text
groupId : artifactId : version : classifier nếu có
```

Cần quan sát cả kiểu đóng gói nếu cơ chế resolve của dự án phân biệt các biến thể theo thông tin đó.

Ví dụ một bộ mô tả cấu trúc cho bản Querydsl gốc có biến thể Jakarta tương ứng:

```text
Compile/runtime:
  com.querydsl:querydsl-core:Q_VERSION
  com.querydsl:querydsl-jpa:Q_VERSION:jakarta

Annotation processor path:
  com.querydsl:querydsl-apt:Q_VERSION:jakarta
  Persistence API và dependency mà processor cần
```

`Q_VERSION` phải được thay bằng phiên bản đã đối chiếu. Sơ đồ này không chứng nhận một phiên bản bất kỳ và không áp nguyên xi cho cách đóng gói của mọi fork.

Với bộ phát hành đồng bộ, nên giữ core, adapter và processor cùng bộ tương thích đã được công bố. Nếu có lý do dùng khác phiên bản, cần bằng chứng cụ thể về tương thích, không chỉ thấy cả ba artifact đều resolve được.

### 6.3. Hai biến thể namespace cũng có thể gây trùng lớp

Không chỉ khác group mới có rủi ro. Hai biến thể như:

```text
Một querydsl-jpa mặc định của bộ phát hành
Một querydsl-jpa có classifier dành cho namespace khác
```

có thể cùng chứa các lớp Querydsl JPA có tên giống nhau.

Nếu bộ quản lý dependency coi chúng là các tọa độ hoặc biến thể khác nhau, cả hai có thể xuất hiện trên classpath. Cần kiểm tra đúng artifact cùng classifier, thay vì chỉ đếm có một số phiên bản Querydsl hay không.

## 7. Kiểm tra phiên bản đã resolve, không chỉ phiên bản đã khai báo

File khai báo dependency mô tả ý định. Kết quả cuối có thể chịu ảnh hưởng của:

- BOM, parent và constraint.
- Dependency bắc cầu.
- Override phiên bản.
- Exclusion và quy tắc thay thế dependency.
- Lockfile hoặc cấu hình resolve.
- Classpath riêng của annotation processor và test.

Ví dụ, dự án có thể khai báo adapter theo một họ nhưng một thư viện trung gian lại đưa core của họ khác vào runtime. Đọc đúng một dòng khai báo adapter sẽ bỏ sót vấn đề này.

Khi xem dependency graph, trả lời các câu hỏi cụ thể:

1. Có artifact Querydsl nào xuất hiện dưới cả hai group không?
2. Core và adapter đến từ bộ nào?
3. Có cả hai biến thể JPA không?
4. Processor path có cùng nhánh và namespace với compile classpath không?
5. Runtime đóng gói có khác compile hoặc test classpath không?
6. Có dependency nào bị thay thế, bị loại hoặc bị ép phiên bản không?

Một quy tắc hội tụ dependency chỉ kiểm tra cùng group và artifact có thể không nhận diện được hai JAR khác group nhưng trùng package. Khi cần, phải dùng khả năng kiểm tra trùng lớp hoặc kiểm tra nội dung classpath thích hợp.

Annotation processor thường chỉ cần ở thời điểm biên dịch. Đưa nó cùng toàn bộ dependency của nó vào runtime không phải cách thay thế cho cấu hình processor path đúng, và có thể kéo thêm các thư viện ngoài dự kiến.

## 8. Chẩn đoán lỗi theo đúng lớp nguyên nhân

Một triệu chứng có thể có nhiều nguyên nhân. Bảng dưới đây chỉ định hướng điều cần kiểm tra:

| Triệu chứng | Khả năng cần kiểm tra | Bằng chứng cần thu thập |
| --- | --- | --- |
| Không tìm thấy QCustomer khi biên dịch | Processor chưa chạy, không nhận diện annotation, sai output hoặc source set | Cấu hình APT và generated sources của build sạch |
| Processor không tìm thấy kiểu persistence | Processor path thiếu API hoặc dùng sai namespace | Dependency riêng của processor và annotation domain |
| Không truyền được EntityManager vào API Querydsl JPA | Adapter và ứng dụng dùng hai namespace khác nhau | Kiểu đầy đủ của tham số cùng constructor thực tế |
| NoClassDefFoundError liên quan javax/persistence hoặc jakarta/persistence | Thiếu thư viện runtime hoặc nạp biến thể không phù hợp | Runtime dependency graph và JAR chứa lớp gọi |
| NoSuchMethodError trong lớp Querydsl | Lớp lúc chạy khác API đã dùng để biên dịch | Bộ JAR thực tế ở compile và runtime |
| Có lớp trùng package Querydsl | Trộn nhánh hoặc trộn biến thể | Danh sách JAR chứa cùng tên lớp |
| IDE chạy được nhưng CI sạch lỗi | Dùng output cũ, JDK khác hoặc cấu hình processor khác | Toolchain, cấu hình build và output được tạo lại |
| Repository không khởi tạo được | Module thiếu hỗ trợ hoặc cấu hình tích hợp chưa đúng | Lỗi gốc và phạm vi hỗ trợ của module đúng phiên bản |

Không xử lý mọi lỗi bằng cách tăng phiên bản Querydsl. Một dependency còn tồn tại dưới group khác, một classifier sai hoặc một processor path thiếu API sẽ không tự được sửa chỉ vì số phiên bản tăng lên.

### 8.1. Phân biệt lỗi thiếu lớp với lỗi sai chữ ký

`NoClassDefFoundError` gợi ý một lớp cần thiết không nạp được, nhưng phải xem đầy đủ nguyên nhân và lớp nào đang tham chiếu tới nó.

`NoSuchMethodError` thường cho thấy mã đã được biên dịch với một API nhưng lớp được nạp lúc chạy không cung cấp chữ ký đó. Đây là lý do cần kiểm tra runtime thay vì chỉ nhìn dependency khai báo trực tiếp.

Nếu cần xác định nguồn của một lớp trong môi trường chẩn đoán, có thể kiểm tra thông tin code source:

```java
Class<?> type = com.querydsl.core.types.Predicate.class;

java.security.CodeSource source =
    type.getProtectionDomain().getCodeSource();

System.out.println(
    source == null
        ? "Không có thông tin code source"
        : source.getLocation()
);
```

Thông tin này hỗ trợ xác định nơi nạp lớp trong môi trường cụ thể. Nó không thay thế việc xem toàn bộ dependency graph, nhất là với cách đóng gói hoặc classloader đặc biệt.

### 8.2. Kiểm tra import đúng đối tượng

Các tên ngắn giống nhau có thể gây hiểu nhầm:

```text
Predicate của Querydsl
    khác Predicate của java.util.function

EntityManager của javax.persistence
    khác EntityManager của jakarta.persistence
```

Lỗi do import nhầm không nhất thiết là lỗi phiên bản. Cần xác định tên lớp đầy đủ trước khi thay đổi dependency.

## 9. Quy trình chọn hoặc nâng cấp một bộ tương thích

### Bước 1: xác định nền tảng cần giữ

Ghi rõ JDK, release train Spring Data và module lưu trữ mà ứng dụng sẽ dùng. Nếu nâng cấp nền tảng, xác định bộ đích trước khi chọn các artifact Querydsl.

### Bước 2: chọn họ Querydsl được bộ đích hỗ trợ

Đối chiếu đúng tài liệu release. Ghi đầy đủ group, version và phạm vi hỗ trợ của module.

Không đổi họ chỉ vì nhìn thấy một ví dụ có số phiên bản cao hơn. Quyết định cần dựa trên tương thích và nhu cầu thực tế của dự án.

### Bước 3: thống nhất adapter và namespace

Với JPA, đối chiếu domain, provider, API persistence và biến thể Querydsl JPA. Với loại kho khác, dùng ma trận của adapter tương ứng.

### Bước 4: đồng bộ processor và classpath

Chọn core, adapter, processor cùng bộ đã được xác minh. Kiểm tra các dependency bắc cầu, classifier và processor path độc lập.

Nếu loại artifact của họ cũ, kiểm tra các đường đưa nó vào dependency graph thay vì chỉ đổi một dependency trực tiếp.

### Bước 5: tạo lại Q-type bằng quy trình build chuẩn

Tạo lại generated sources từ cấu hình đã khai báo. Đảm bảo CI có thể thực hiện cùng quy trình với JDK và toolchain dự kiến.

Không coi việc các Q-type cũ còn biên dịch là bằng chứng đầy đủ cho bộ processor mới.

### Bước 6: kiểm tra tích hợp thực tế theo module

Việc biên dịch chứng minh được một phần tương thích API ở compile time. Việc khởi tạo repository và thực thi truy vấn tối thiểu cung cấp bằng chứng cho đường tích hợp runtime.

Sau đó kiểm tra những khả năng ứng dụng thực sự dùng, chẳng hạn predicate trên trường lồng nhau, sắp xếp, phân trang hoặc projection. Một truy vấn đơn giản thành công không chứng minh toàn bộ API đều được hỗ trợ.

### Bước 7: ghi lại bộ cuối cùng

Ghi quyết định phiên bản và các dependency đã resolve theo quy ước dự án. Bộ cuối cần có đủ thông tin để tái tạo trên CI, thay vì phụ thuộc cache IDE hoặc thứ tự classpath tình cờ.

## 10. Ví dụ kiểm tra đường tích hợp Commons

Giả sử domain Customer có thuộc tính country và QCustomer đã được sinh đúng.

Repository:

```java
import org.springframework.data.repository.Repository;
import org.springframework.data.querydsl.QuerydslPredicateExecutor;

public interface CustomerRepository
        extends Repository<Customer, Long>,
                QuerydslPredicateExecutor<Customer> {
}
```

Đoạn truy vấn trong một thành phần đã được cung cấp repository:

```java
import com.querydsl.core.types.Predicate;

QCustomer customer = QCustomer.customer;

Predicate inVietnam = customer.country.eq("VN");

boolean found =
    customerRepository.exists(inVietnam);
```

Đường kiểm tra này liên quan tới:

1. Q-type được tạo và biên dịch.
2. Kiểu Predicate có mặt với API phù hợp.
3. Repository implementation của module được cấu hình.
4. Adapter có thể dịch và thực thi điều kiện trên kho.

Kết quả true hay false phụ thuộc dữ liệu; cả hai đều có thể hợp lệ. Mục tiêu ở đây là kiểm tra đường tích hợp, không khẳng định một tập dữ liệu cụ thể phải tồn tại.

Đây không phải cách kiểm tra mọi tính năng Querydsl. Nếu ứng dụng cần truy vấn trực tiếp bằng API của adapter, projection đặc biệt hoặc các cấu trúc truy vấn sâu hơn, cần xác minh thêm đúng đường sử dụng đó.

## 11. Ba tình huống đối chiếu

### Tình huống A: domain Jakarta, adapter còn dùng javax

Dấu hiệu có thể là constructor không nhận EntityManager của ứng dụng, hoặc lỗi nạp lớp persistence lúc chạy.

Hướng giải quyết:

- Xác nhận namespace của domain và provider.
- Chọn biến thể adapter phù hợp trong nhánh đã được hỗ trợ.
- Đối chiếu lại processor và dependency persistence.
- Tạo lại Q-type cùng bộ cấu hình mới.

Thêm cả hai persistence API chỉ để làm biến mất lỗi thiếu lớp chưa giải quyết sự khác nhau giữa hai kiểu EntityManager.

### Tình huống B: đã đổi group adapter nhưng runtime còn core của nhánh cũ

Import vẫn bắt đầu bằng com.querydsl nên mã nguồn nhìn có vẻ nhất quán. Nhưng dependency graph có thể chứa hai JAR định nghĩa cùng lớp.

Hướng giải quyết là tìm đường dependency đưa artifact còn lại vào, điều chỉnh quản lý dependency hoặc exclusion có chủ đích, rồi xác minh lại cả compile, processor và runtime.

Đổi import hàng loạt theo group artifact mới không giải quyết vấn đề trùng lớp.

### Tình huống C: chạy được trên IDE nhưng không sinh Q-type trên CI

Khả năng cần kiểm tra gồm processor không được kích hoạt, thiếu dependency trên processor path, JDK khác hoặc generated sources cũ che khuất lỗi.

Hướng giải quyết là làm cho quy trình build chính thức khai báo đủ đầu vào và tạo lại mã trên môi trường sạch. Chọn lại phiên bản chỉ có ý nghĩa sau khi xác định có lệch tương thích thật sự.

## 12. Bài tập tự kiểm tra

1. Hai artifact có cùng số phiên bản nhưng khác group có chắc là cùng nhánh Querydsl không?
2. Vì sao fork có group io.github.openfeign.querydsl vẫn có thể dùng import com.querydsl?
3. Nếu domain dùng jakarta.persistence, có thể truyền EntityManager đó vào một API chỉ nhận javax.persistence.EntityManager không?
4. Tại sao đúng dependency runtime vẫn chưa đủ để bảo đảm Q-type được sinh?
5. Sự xuất hiện của javax.annotation.processing.Generated trong Q-type có tự chứng minh dùng sai JPA namespace không?
6. Vì sao cần xem classifier khi kiểm tra trùng artifact?
7. Build trên IDE thành công nhưng CI sạch lỗi cho thấy cần kiểm tra những gì?
8. QuerydslPredicateExecutor biên dịch được có bảo đảm mọi module lưu trữ đều thực thi được không?

Gợi ý đáp án:

1. Không. Cần xác định họ phân phối và tọa độ đầy đủ.
2. Vì group dependency và package Java là hai định danh khác nhau; fork có thể giữ package.
3. Không. Đó là hai kiểu Java khác nhau.
4. Processor có classpath, dependency và cấu hình kích hoạt riêng.
5. Không. Annotation đó thuộc API xử lý annotation của JDK.
6. Các biến thể có thể chứa cùng tên lớp nhưng được resolve như các tọa độ khác nhau.
7. JDK, toolchain, processor path, cấu hình APT, source set và generated output được tạo lại.
8. Không. Module cần có implementation và hỗ trợ tương ứng.

Nguyên tắc chọn bộ thư viện là đối chiếu theo toàn bộ chuỗi từ nền tảng, nhánh Querydsl và namespace đến sinh mã và runtime. Một cấu hình tương thích phải tái tạo được bằng quy trình build rõ ràng và thực thi được những đường truy vấn mà ứng dụng sử dụng.
