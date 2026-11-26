# Giới hạn của dynamic projection, proxy, Querydsl hoặc Kotlin trong môi trường AOT

Trong Spring Data Commons, `Repository`, truy vấn suy diễn từ tên phương thức, phân trang, sắp xếp, projection và auditing giúp ứng dụng truy cập dữ liệu bằng những abstraction dùng chung. Nhiều abstraction dựa vào metadata của kiểu, proxy, reflection hoặc thành phần tích hợp với từng kho dữ liệu. Khi chuyển ứng dụng sang AOT, những cơ chế đó cần được xem xét trong một mô hình mà nhiều quyết định phải được xác định từ lúc build.

Bài này thuộc chương **Phiên bản và AOT**, tập trung vào bốn nhóm dễ phát sinh giới hạn: dynamic projection, proxy, Querydsl và Kotlin. Mục tiêu là nhận diện điểm nào còn động ở thời điểm chạy, điểm nào phải được khai báo hoặc sinh trước, và cách thiết kế repository để hành vi có thể kiểm chứng trên artifact đích.

Không có một kết luận chung rằng cả bốn nhóm đều không chạy được với AOT. Mức hỗ trợ phụ thuộc tổ hợp Spring Framework, Spring Boot nếu sử dụng, Spring Data, module kho dữ liệu, thư viện tích hợp và công cụ build native. Vì vậy, các ví dụ dưới đây minh họa nguyên tắc thiết kế; chúng không thay thế việc đối chiếu khả năng hỗ trợ của bộ phiên bản cụ thể trong dự án.

## 1. Phân biệt AOT processing và native image

### 1.1. AOT xử lý trước những gì có thể biết từ cấu hình ứng dụng

AOT processing của Spring phân tích ứng dụng trong giai đoạn build để sinh mã khởi tạo và metadata cần thiết. Với Spring Data, thông tin về repository, domain type, phương thức truy vấn và projection có thể là đầu vào cho các bước xử lý liên quan, tùy phiên bản và module.

Điểm cần chú ý là cấu trúc ứng dụng mà AOT quan sát được: bean nào tồn tại, kiểu repository nào được khai báo, các cấu hình điều kiện nào được kích hoạt. Nếu ứng dụng chỉ quyết định thêm một kiểu repository hoặc một bean hoàn toàn mới sau khi artifact đã được tạo, cấu trúc đó có thể không nằm trong kết quả phân tích.

Điều này không có nghĩa mọi giá trị đều phải cố định lúc build. Tham số truy vấn, số trang, kích thước trang, khóa sắp xếp hợp lệ hoặc giá trị của bộ lọc vẫn có thể thay đổi lúc chạy. Cần tách **dữ liệu biến thiên** khỏi **tập kiểu và cơ chế khởi tạo mà chương trình cần dùng**.

### 1.2. Native image bổ sung ràng buộc về tập kiểu và metadata

Native image xây dựng chương trình dựa trên tập mã và kiểu có thể được tiếp cận trong lúc phân tích. Reflection, resource và JDK dynamic proxy có thể cần metadata bổ sung khi công cụ không suy ra được cách sử dụng. Không thể giả định việc nạp một lớp tùy ý hoặc sinh một lớp mới lúc chạy có hành vi giống JVM thông thường.

AOT processing và native compilation có liên quan nhưng không đồng nghĩa. Một ứng dụng có thể chạy trên JVM thông thường, chạy bằng mã khởi tạo AOT trên JVM, rồi vẫn gặp lỗi trên native executable do một đường reflection chưa được bao phủ.

| Chế độ | Giá trị của việc kiểm tra | Điều chưa được chứng minh |
| --- | --- | --- |
| JVM thông thường | Logic repository và ánh xạ hoạt động trong cấu hình JVM | Khả năng xử lý AOT và metadata cho native |
| JVM dùng kết quả AOT, nếu công cụ hỗ trợ | Cấu hình và mã khởi tạo được sinh có thể chạy | Toàn bộ giới hạn của native runtime |
| Native executable | Hành vi thật của artifact native với các ca đã chạy | Các nhánh projection, truy vấn hoặc cấu hình chưa được gọi |

Một lần khởi động thành công chỉ cho thấy đường khởi động được kiểm tra đã hoạt động. Nó chưa chứng minh rằng projection ít dùng, truy vấn Querydsl riêng hoặc nhánh constructor Kotlin đều hợp lệ.

## 2. Bản đồ rủi ro của bốn nhóm tính năng

| Nhóm | Phần có thể cần biết trước | Rủi ro khi dùng quá động | Hướng xử lý chính |
| --- | --- | --- | --- |
| Dynamic projection | Các kiểu đích và cách dựng đối tượng | Kiểu truyền qua `Class<T>` không được phân tích hoặc không có metadata cần thiết | Giới hạn kiểu đích và kiểm tra từng kiểu |
| Proxy | Interface, tổ hợp interface, phương thức cần gọi | Proxy cần lúc chạy khác với tập đã được hỗ trợ hoặc khai báo | Dùng cơ chế tích hợp của framework và kiểm tra đúng proxy thực tế |
| Querydsl | Q-types, thư viện tích hợp, cách thực thi truy vấn | Q-type tồn tại nhưng đường ánh xạ hoặc tích hợp vẫn cần cơ chế động | Kiểm tra cả chuỗi từ sinh mã đến thực thi truy vấn |
| Kotlin | Constructor, nullability, metadata Kotlin, cách tạo proxy nếu có | Khác biệt bytecode và quy tắc ngôn ngữ không được mapper hoặc công cụ xử lý đúng | Dùng mô hình Kotlin rõ ràng và kiểm tra mapping trên artifact đích |

Spring Data Commons cung cấp abstraction chung; module như JPA, MongoDB hoặc JDBC quyết định nhiều chi tiết thực thi. Kết quả kiểm tra ở một module không tự trở thành cam kết cho module khác.

## 3. Dynamic projection: generic không có nghĩa là tập kiểu vô hạn

### 3.1. Cơ chế trên repository

Ví dụ một repository khai báo projection động:

```java
import java.util.List;
import org.springframework.data.repository.Repository;

public interface PersonRepository extends Repository<Person, Long> {
    <T> List<T> findByLastName(String lastName, Class<T> projectionType);
}
```

Các kiểu đích minh họa:

```java
public interface NamesOnly {
    String getFirstName();
    String getLastName();
}
```

```java
public record PersonSummary(String firstName, String lastName) {
}
```

Bên gọi lựa chọn kiểu kết quả:

```java
List<NamesOnly> names =
        repository.findByLastName("Nguyen", NamesOnly.class);

List<PersonSummary> summaries =
        repository.findByLastName("Nguyen", PersonSummary.class);
```

`Class<T>` giúp Spring Data nhận biết kiểu projection cho lần gọi tương ứng, khi chữ ký đáp ứng quy tắc nhận diện dynamic projection. Nó không tự chứng minh rằng mọi lớp có thể được truyền vào đều được hỗ trợ bởi module kho dữ liệu hoặc đã có metadata phù hợp trong native image.

Cũng cần phân biệt tham số chọn projection với tham số dùng trong chính truy vấn. Khi Spring Data nhận một tham số `Class` là bộ chọn dynamic projection, tham số đó không được coi như tham số truy vấn thông thường. Nếu thực sự cần truyền một giá trị `Class` vào truy vấn, phải thiết kế chữ ký theo quy tắc của module và tránh nhầm hai vai trò.

### 3.2. Ba câu hỏi phải trả lời cho từng kiểu đích

1. **Framework có nhận biết kiểu này trong quá trình xử lý hay không?** Kiểu xuất hiện rõ trong chữ ký repository thường dễ phân tích hơn một tên lớp đọc từ cấu hình lúc chạy. Khả năng xử lý dynamic projection cụ thể vẫn cần đối chiếu với bộ phiên bản đang dùng.
2. **Có cơ chế dựng kết quả phù hợp hay không?** Interface projection thường cần proxy; DTO cần constructor hoặc đường ánh xạ thích hợp. Một lớp tồn tại trong binary chưa có nghĩa mọi constructor cần gọi qua reflection đều sẵn sàng.
3. **Module kho dữ liệu có tạo và ánh xạ kết quả đúng hay không?** Việc chọn trường, viết lại truy vấn, gọi constructor hoặc trả tuple phụ thuộc module và loại truy vấn.

Đây là ba lớp vấn đề khác nhau. Thêm reflection hint cho DTO không sửa được một truy vấn sai hoặc một dạng projection mà module không hỗ trợ.

### 3.3. Tập lựa chọn hữu hạn dễ kiểm soát hơn tên lớp tùy ý

Một API nhận tên lớp từ request rồi dùng `Class.forName(...)` để chọn projection làm tập kiểu đích khó xác định. Nếu lớp chỉ được cung cấp sau lúc build, metadata không thể biến native executable thành môi trường nạp kiểu tùy ý giống JVM.

Một thiết kế dễ kiểm tra hơn là ánh xạ lựa chọn nghiệp vụ sang tập projection xác định trước:

```java
public enum PersonView {
    NAMES,
    SUMMARY
}
```

```java
public Object findPeople(String lastName, PersonView view) {
    return switch (view) {
        case NAMES -> repository.findByLastName(lastName, NamesOnly.class);
        case SUMMARY -> repository.findByLastName(lastName, PersonSummary.class);
    };
}
```

Kiểu trả về `Object` ở đây chỉ để làm gọn ví dụ bộ chọn. Ở API thực tế, nên dùng hợp đồng trả về rõ ràng cho từng endpoint hoặc một mô hình response thống nhất. Đặc biệt, việc gom nhánh bằng `switch` giúp biết tập kiểu cần kiểm tra, nhưng tự nó không đảm bảo AOT sẽ tự sinh đủ metadata cho mọi projection.

Khi ứng dụng chỉ có vài nhu cầu ổn định, các phương thức có kiểu trả về cụ thể có thể rõ hơn:

```java
public interface PersonRepository extends Repository<Person, Long> {
    List<NamesOnly> findNamesByLastName(String lastName);
    List<PersonSummary> findSummaryByLastName(String lastName);
}
```

Các từ mô tả giữa `find` và `By` giúp phân biệt hai phương thức; điều kiện vẫn dựa vào thuộc tính `lastName`. Cách đặt tên này không đảm bảo mọi module đều hỗ trợ cùng kiểu ánh xạ projection. Cần xác minh riêng chữ ký và kiểu kết quả trong module đang dùng.

### 3.4. Closed, open và nested projection có bề mặt khác nhau

Với interface projection chỉ khai báo accessor tương ứng thuộc tính, framework có tập thuộc tính tương đối rõ để phân tích. Open projection dùng biểu thức, ví dụ `@Value` với SpEL, có thể phụ thuộc thêm vào thuộc tính, bean hoặc lời gọi phương thức. Nested projection có thể kéo theo các interface và đường truy cập khác.

Không nên biến nhận xét này thành quy tắc “closed projection luôn chạy native, open projection luôn không chạy”. Kết quả phụ thuộc hỗ trợ cụ thể. Điều cần làm là kiểm tra đầy đủ các phương thức accessor, biểu thức và projection lồng nhau mà ứng dụng thực sự sử dụng.

Đối với DTO, constructor rõ ràng thường dễ phân tích. Java record có constructor chuẩn phù hợp với mô hình giá trị, nhưng record không miễn trừ các yêu cầu về mapper, tên tham số hoặc query rewriting của module. DTO có nhiều constructor cần một cách chọn constructor không mơ hồ theo quy tắc Spring Data phù hợp.

## 4. Proxy: cần phân biệt repository, projection và domain object

### 4.1. Các proxy giải quyết những việc khác nhau

Trong một ứng dụng, từ “proxy” có thể chỉ nhiều đối tượng:

- **Repository proxy** chuyển lời gọi interface sang query method, repository fragment hoặc triển khai nền.
- **Projection proxy** cung cấp các accessor của interface projection từ nguồn dữ liệu phù hợp.
- **Proxy của domain object hoặc ORM**, nếu module và provider có sử dụng, phục vụ những chức năng riêng như lazy loading.
- **Proxy do ứng dụng hoặc thư viện bổ sung**, chẳng hạn một lớp bọc phục vụ logging hoặc interception.

Các nhóm này không dùng chung một cấu hình duy nhất. Hint cho projection không tự giải quyết proxy của ORM. Thay đổi cách tạo proxy ở một lớp hạ tầng cũng không bảo đảm toàn bộ repository và projection đổi cơ chế theo.

### 4.2. JDK dynamic proxy cần đúng tổ hợp interface

JDK dynamic proxy hoạt động dựa trên interface. Với native image, việc tạo proxy cần được công cụ phân tích hoặc có metadata phù hợp. Framework có thể tự đóng góp thông tin cho những trường hợp nó hỗ trợ.

Điểm dễ bỏ sót là proxy thực tế có thể triển khai thêm interface hạ tầng. Chỉ nhìn thấy interface nghiệp vụ rồi khai báo một proxy hint cho riêng interface đó có thể chưa khớp yêu cầu lúc chạy. Nếu phải bổ sung thủ công, cần xác định đúng danh sách và thứ tự interface theo cơ chế mà runtime sử dụng, thay vì đoán theo tên repository.

Không nên tự đăng ký một tập lớn mọi interface trong ứng dụng để làm lỗi biến mất. Một đăng ký không khớp không thay thế đăng ký cần thiết; tập hint rộng còn làm khó việc xác định framework hay mã tùy biến mới là nơi thiếu hỗ trợ.

### 4.3. Proxy dựa trên lớp và sinh bytecode cần xem xét riêng

Proxy dựa trên lớp có thể liên quan đến việc tạo subclass. Một cơ chế sinh subclass hoạt động trên JVM chưa chắc được hỗ trợ theo cùng cách trong native runtime. Một số tích hợp có thể sinh trước hoặc xử lý riêng; khả năng đó phải được kiểm tra với đúng framework và provider.

Từ đây xuất hiện hai kết luận thực tế:

- Interface-based design thường giúp hợp đồng repository rõ hơn, nhưng không tự bảo đảm tất cả proxy liên quan đã có metadata.
- Reflection hint không cấp khả năng sinh bytecode tùy ý lúc chạy. Nếu thư viện cần cơ chế đó mà không có đường AOT tương ứng, phải thay cách tích hợp hoặc cách triển khai.

### 4.4. Khi nào dùng runtime hints?

Ưu tiên dùng cơ chế AOT và hint được cung cấp bởi Spring Data, module kho dữ liệu và thư viện tương thích. Chỉ bổ sung hint của ứng dụng khi đã xác định một nhu cầu cụ thể, chẳng hạn mã tùy biến đọc một DTO đã biết qua reflection.

Ví dụ dưới đây minh họa đăng ký constructor và phương thức công khai cho một DTO cụ thể. Đây là ví dụ về API hints của Spring Framework, không phải cấu hình bắt buộc cho mọi DTO Spring Data:

```java
import org.springframework.aot.hint.MemberCategory;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;

public final class PersonReflectionHints implements RuntimeHintsRegistrar {
    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        hints.reflection().registerType(
                PersonSummary.class,
                MemberCategory.INVOKE_DECLARED_CONSTRUCTORS,
                MemberCategory.INVOKE_PUBLIC_METHODS);
    }
}
```

Khai báo registrar bằng cấu hình phù hợp, ví dụ:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.ImportRuntimeHints;

@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(PersonReflectionHints.class)
class PersonNativeConfiguration {
}
```

Nếu framework đã tự cung cấp đủ thông tin, đăng ký này có thể không cần thiết. Nếu lỗi nằm ở proxy, resource, query rewriting hoặc sinh lớp, đăng ký reflection cho `PersonSummary` cũng có thể không liên quan. Cần thu hẹp đăng ký đến đúng thành viên mà đường thực thi cần.

Runtime hints có phạm vi riêng cho reflection, proxy, resource và những loại metadata được công cụ hỗ trợ. Một loại hint không thay thế tất cả các loại còn lại.

## 5. Querydsl: sinh Q-type mới hoàn thành một phần chuỗi xử lý

### 5.1. Hai hoạt động thường bị nhầm

Querydsl tạo metamodel như `QPerson` trong giai đoạn build bằng annotation processing thích hợp. Chương trình sau đó dùng metamodel này để xây dựng biểu thức truy vấn có kiểu.

Ví dụ ý tưởng khi module đang dùng hỗ trợ `QuerydslPredicateExecutor`:

```java
import org.springframework.data.querydsl.QuerydslPredicateExecutor;
import org.springframework.data.repository.Repository;

public interface PersonQueryRepository
        extends Repository<Person, Long>,
                QuerydslPredicateExecutor<Person> {
}
```

```java
QPerson person = QPerson.person;
Iterable<Person> result = repository.findAll(
        person.lastName.eq("Nguyen"));
```

`QPerson` là mã được sinh trong build và phải có trong compilation tương ứng. Tuy nhiên, Q-type tồn tại không chứng minh rằng việc lấy query executor, chuyển biểu thức sang truy vấn, ánh xạ kết quả và tích hợp với provider đều tương thích native.

### 5.2. Cần kiểm tra cả chuỗi

```text
Domain model
    -> annotation processing
    -> Q-types được sinh và biên dịch
    -> tích hợp Querydsl của module kho dữ liệu
    -> dựng và thực thi truy vấn
    -> ánh xạ kết quả hoặc projection
    -> artifact native thực thi đường gọi này
```

Các điểm cần phân biệt:

| Dấu hiệu | Phạm vi cần xem xét |
| --- | --- |
| Không tìm thấy `QPerson` khi biên dịch | Annotation processor, thứ tự biên dịch, generated sources và dependency |
| Không tạo được repository hoặc query executor | Khả năng tích hợp của module, cấu hình bean và phiên bản thư viện |
| Truy vấn entity chạy nhưng DTO projection lỗi | Cơ chế projection, constructor và ánh xạ kết quả |
| JVM chạy nhưng native lỗi trên một truy vấn | Metadata, cơ chế động hoặc giới hạn của đường tích hợp cụ thể |

Không nên gộp cả bốn tình huống thành “thiếu reflection hint”. Lỗi sinh Q-type xuất hiện trước native runtime; một hint không thể tạo lại mã nguồn đã thiếu trong bước biên dịch.

### 5.3. Kiểu biểu thức ảnh hưởng đến nhu cầu metadata

Trong hệ sinh thái Querydsl, các kiểu projection có thể dùng constructor, setter, field hoặc mã constructor expression được sinh trước. Chúng có bề mặt reflection khác nhau. Không thể kết luận mọi kiểu projection Querydsl đều có cùng yêu cầu chỉ vì chúng trả về cùng một DTO.

Mã sinh cho constructor expression có thể làm lời gọi constructor rõ hơn trong một số đường thực thi. Tuy vậy, nó không chứng minh rằng provider, serializer, binding từ request hoặc phần tích hợp Spring Data đã hết phụ thuộc động. Cần kiểm tra đường thực thi thật thay vì suy luận từ một đoạn mã được sinh.

Tương tự, xây predicate bằng Q-type trực tiếp và tạo predicate từ tham số HTTP thông qua cơ chế binding là hai đường khác nhau. Trường hợp thứ hai có thể bổ sung truy cập thuộc tính, conversion và metadata. Chạy thành công một predicate viết tay chưa bao phủ việc binding.

### 5.4. Phương án khi đường tích hợp chưa phù hợp

Nếu tổ hợp Querydsl và module hiện tại chưa hỗ trợ một nhu cầu trên artifact đích, có thể thu hẹp sang:

- Derived query cho điều kiện nghiệp vụ ổn định, chẳng hạn tìm theo họ và trạng thái.
- Query được khai báo rõ trong module kho dữ liệu đang dùng.
- Repository fragment có triển khai sử dụng API truy vấn mà module hỗ trợ trong môi trường đích.

Ví dụ hợp đồng đơn giản hơn:

```java
List<PersonSummary> findSummaryByLastNameAndActive(
        String lastName, boolean active);
```

Lựa chọn này giảm mức động của hợp đồng, nhưng vẫn cần kiểm tra projection và mapping. Nếu hệ thống thực sự cần tổ hợp bộ lọc linh hoạt, nên xác định một mô hình bộ lọc có trường và toán tử được hỗ trợ, rồi kiểm tra cách chuyển mô hình đó sang API truy vấn của module. Giá trị bộ lọc có thể động mà không cần cho phép kiểu Java tùy ý.

## 6. Kotlin: xem xét constructor, nullability và proxy theo đúng module

### 6.1. Kotlin không đồng nghĩa với bất tương thích AOT

Spring Data có cơ chế hỗ trợ mô hình Kotlin trong các phạm vi nhất định. AOT không làm mọi `data class` trở thành không dùng được. Vấn đề nằm ở tổ hợp giữa bytecode Kotlin, metadata ngôn ngữ, cách Spring Data ánh xạ đối tượng và provider cụ thể.

Một domain model minh họa cho module có hỗ trợ ánh xạ constructor:

```kotlin
data class Person(
    val id: Long?,
    val firstName: String,
    val lastName: String,
    val nickname: String? = null
)
```

Ví dụ này minh họa mô hình giá trị và nullability. Nó không phải mẫu entity có thể sao chép nguyên trạng cho mọi module; quy tắc định danh, constructor và annotation còn phụ thuộc kho dữ liệu.

Các câu hỏi cần kiểm tra gồm:

- Constructor nào được chọn để tạo đối tượng?
- Tên tham số và metadata cần cho mapping có sẵn trong artifact không?
- Tham số nullable và non-null được xử lý thế nào với dữ liệu thật?
- Tham số có giá trị mặc định có được mapper sử dụng trong trường hợp đang xét không?
- Một phần tích hợp có cần Kotlin reflection hoặc dependency Kotlin liên quan không?

Dependency xuất hiện trong classpath không tự đảm bảo mọi lời gọi reflection qua nó đều được hỗ trợ trong native executable.

### 6.2. Giá trị mặc định không phải phép sửa dữ liệu chung

Giả sử `nickname` có giá trị mặc định. Việc mapper có bỏ qua một tham số để sử dụng giá trị mặc định phụ thuộc cơ chế ánh xạ và dữ liệu mà module cung cấp. Không nên suy ra rằng mọi cột hoặc field bị `null` đều sẽ được đổi thành giá trị mặc định của Kotlin.

Đặc biệt, dữ liệu `null` cho một thuộc tính `String` không nullable có thể là vấn đề giữa schema và domain model, không phải lỗi AOT. Hãy so sánh cùng dữ liệu trên JVM và native để xác định ranh giới. Không thêm reflection hint nhằm che một hợp đồng nullability không đúng.

### 6.3. `final`, `open` và no-arg giải quyết các vấn đề khác nhau

Lớp và phương thức Kotlin mặc định là `final`. Nếu một cơ chế tích hợp cần tạo subclass, tính chất này có thể ảnh hưởng đến proxy. Interface projection và repository interface có hợp đồng khác với entity hoặc bean cần proxy dựa trên lớp.

Compiler plugin như all-open hoặc no-arg chỉ nên áp dụng theo yêu cầu của công nghệ đang dùng:

| Cơ chế | Mục đích liên quan | Điều không tự giải quyết |
| --- | --- | --- |
| All-open hoặc cơ chế mở lớp có chọn lọc | Cho phép kế thừa theo quy tắc plugin và annotation | Metadata reflection hoặc khả năng sinh proxy trong native runtime |
| No-arg hoặc plugin dành cho mô hình persistence phù hợp | Sinh constructor không tham số theo quy tắc cấu hình | Constructor mapping cho mọi module Spring Data |
| Runtime hints | Khai báo truy cập động cụ thể cho các kiểu đã biết | Quy tắc ngôn ngữ, hợp đồng entity hoặc hỗ trợ framework còn thiếu |

Không cần biến mọi lớp Kotlin thành `open` hoặc thêm no-arg cho mọi `data class`. Với mô hình ánh xạ bằng constructor, một constructor chính rõ ràng có thể là lựa chọn phù hợp. Với ORM có yêu cầu riêng về entity và proxy, cần xử lý đúng yêu cầu của ORM đó.

### 6.4. Kotlin projection và coroutine là các nhánh riêng

Một DTO Kotlin có constructor được dùng để ánh xạ là trường hợp khác với interface projection trả về kiểu Kotlin nullable. Cả hai cần kiểm tra mapping, nhưng interface projection còn có đường proxy tương ứng.

Nếu repository sử dụng `suspend` hoặc `Flow`, cần kiểm tra hỗ trợ coroutine của module kho dữ liệu đang dùng cùng đường thực thi AOT/native. Không nên lấy kết quả của repository đồng bộ làm bằng chứng cho repository coroutine. Đồng thời, chuyển sang coroutine không loại bỏ yêu cầu metadata của domain type hoặc projection.

## 7. Phân trang, sắp xếp và auditing liên quan thế nào?

Các abstraction dùng chung vẫn phải đi qua đường thực thi cụ thể:

- `Pageable` và `Sort` chứa giá trị có thể thay đổi lúc chạy. Số trang hay hướng sắp xếp không cần cố định khi build. Đường thuộc tính sắp xếp vẫn phải hợp lệ và cách module diễn giải nó phải được hỗ trợ.
- `Page<Projection>` bổ sung đường ánh xạ projection; với trường hợp cần truy vấn đếm, cả truy vấn lấy dữ liệu và truy vấn đếm đều cần hoạt động.
- Auditing có thể đi qua callback, listener, truy cập thuộc tính hoặc provider thời gian/người dùng. Tùy module, đường đó cần được kiểm tra khi ghi dữ liệu.

Ví dụ, một ứng dụng chỉ kiểm tra `findById` chưa bao phủ việc điền `createdBy` khi lưu mới hoặc ánh xạ một trang DTO. Phạm vi kiểm tra nên bám vào tính năng mà ứng dụng cung cấp cho người dùng.

Cũng không nên kết luận mọi cơ chế sắp xếp có cùng bề mặt AOT. `Sort.by("lastName")` và một API lấy tên thuộc tính bằng method reference hoặc proxy có thể đi qua cơ chế khác nhau. Nếu dự án dùng cách thứ hai, cần kiểm tra chính API và bộ phiên bản đó trong môi trường đích.

## 8. Cách kiểm tra để có bằng chứng đủ dùng

### 8.1. Chốt bộ cấu hình trước khi so sánh

Ghi nhận bộ phiên bản Spring, Spring Data, module kho dữ liệu, JDK, công cụ native, Querydsl và Kotlin nếu có. Dùng cùng schema, dữ liệu kiểm tra và điều kiện nghiệp vụ khi so sánh JVM với native.

Những cấu hình ảnh hưởng đến sự hiện diện của bean cần được áp dụng nhất quán trong quá trình build AOT. Có thể để giá trị kết nối hoặc thông tin môi trường thay đổi theo cơ chế được hỗ trợ, nhưng không giả định một profile lúc chạy có thể thêm vào artifact một cấu trúc bean mà bước AOT chưa xử lý.

### 8.2. Chọn ma trận theo nhánh tính năng

| Ca kiểm tra | Dữ liệu hoặc thao tác | Bằng chứng cần thu |
| --- | --- | --- |
| Derived query trả domain type | Có kết quả và không có kết quả | Điều kiện truy vấn và mapping cơ bản đúng |
| Mỗi dynamic projection được cho phép | Gọi riêng từng `Class<T>` | Đúng kiểu, đúng trường và gọi được accessor |
| Nested hoặc open projection, nếu sử dụng | Truy cập hết đường lồng nhau hoặc biểu thức | Proxy và các phụ thuộc liên quan hoạt động |
| DTO có constructor | Trường đủ dữ liệu, trường nullable | Constructor selection và mapping đúng |
| Querydsl | Predicate thực tế, projection và binding nếu có | Cả dựng truy vấn lẫn ánh xạ kết quả hoạt động |
| Kotlin | Nullability, default parameter, coroutine nếu có | Hành vi ngôn ngữ và mapping đúng với hợp đồng |
| Phân trang và sắp xếp | Trang đầu, trang rỗng, các khóa được hỗ trợ | Dữ liệu, thứ tự và tổng số đúng nếu có `Page` |
| Auditing | Tạo mới và cập nhật nếu ứng dụng dùng | Các trường kiểm toán được điền đúng |

Không cần tạo mọi tổ hợp toán học giữa các đặc tính. Hãy ưu tiên đường thực thi khác nhau, nhất là đường có proxy, constructor hoặc binding riêng.

### 8.3. Kiểm tra trên artifact cuối cùng

Một chu trình có ý nghĩa gồm:

1. Chạy các ca nghiệp vụ tương ứng trên JVM để có mốc so sánh.
2. Tạo kết quả AOT bằng cấu hình ứng dụng mục tiêu; kiểm tra mã và metadata sinh ra khi cần chẩn đoán.
3. Build artifact native bằng toolchain đã chọn.
4. Chạy các ca quan trọng trên native executable, bao gồm gọi accessor sau khi repository trả kết quả.
5. So sánh nội dung, kiểu kết quả, phân trang và lỗi với hợp đồng mong muốn.

Chỉ gọi repository rồi bỏ kết quả có thể chưa kích hoạt phần truy cập projection hoặc ánh xạ trễ. Các ca kiểm tra cần đọc những trường mà ứng dụng thực sự sử dụng.

Công cụ thu thập metadata trên JVM có thể giúp tìm truy cập động mà phân tích tĩnh chưa nhận diện. Dữ liệu thu được phụ thuộc các đường đã chạy, nên không thay thế việc xác định tập projection và kiểm tra native.

## 9. Chẩn đoán theo triệu chứng

| Triệu chứng | Giả thuyết cần kiểm tra trước | Hành động phù hợp |
| --- | --- | --- |
| Khởi động native được, projection thứ hai mới lỗi | Nhánh kiểu đích chưa được xử lý đầy đủ | Kiểm tra kiểu thứ hai, proxy hoặc constructor và mức hỗ trợ của module |
| Lỗi ngay khi tạo proxy | Tổ hợp interface hoặc cơ chế proxy chưa được hỗ trợ | Xác định proxy thuộc repository, projection hay provider trước khi thêm metadata |
| Không tìm thấy Q-type khi build | Annotation processing hoặc generated sources | Sửa bước sinh và biên dịch Q-type |
| Q-type có nhưng truy vấn vẫn lỗi native | Phần tích hợp, provider hoặc mapping kết quả | Tách thử trả entity và trả DTO để xác định lớp lỗi |
| Kotlin lỗi cả trên JVM | Constructor, nullability hoặc hợp đồng persistence | Sửa mô hình và dữ liệu trước khi điều tra native |
| JVM đúng, Kotlin DTO lỗi native | Metadata hoặc hỗ trợ của đường dựng đối tượng | Xác định constructor và cơ chế gọi thực tế |
| Thêm reflection hint không đổi lỗi | Đang thiếu loại metadata khác hoặc thiếu khả năng hỗ trợ | Đọc nguyên nhân gốc và giảm ví dụ đến đường gây lỗi |

Trình tự hữu ích là xác định đường thực thi, tìm thành phần chịu trách nhiệm, rồi kiểm tra hỗ trợ và metadata của thành phần đó. Tránh thay đồng thời kiểu projection, provider và cấu hình Kotlin vì sẽ khó biết thay đổi nào giải quyết vấn đề.

## 10. Ví dụ quyết định thiết kế cho một màn hình danh sách

Giả sử màn hình quản trị nhân sự cần hai dạng dữ liệu: danh sách tên và thông tin tóm tắt. Người dùng có thể lọc theo họ, phân trang và chọn vài khóa sắp xếp đã được công bố.

Một thiết kế có thể kiểm soát được trong AOT gồm:

1. Khai báo rõ hai projection được phép và module kho dữ liệu chịu trách nhiệm thực thi chúng.
2. Dùng hai phương thức repository có kiểu trả về cụ thể, hoặc dynamic projection với danh sách kiểu đích hữu hạn nếu tích hợp đang dùng hỗ trợ.
3. Ánh xạ lựa chọn từ giao diện sang kiểu đã biết; không biến tên lớp từ request thành kiểu Java tùy ý.
4. Kiểm tra trang dữ liệu và đọc đầy đủ accessor của từng projection trên native executable.
5. Nếu cần Querydsl, kiểm tra thêm đúng đường Querydsl dùng trong màn hình, gồm binding hoặc DTO projection nếu có.
6. Với DTO Kotlin, bổ sung ca dữ liệu nullable và constructor theo đúng mô hình.

Nếu projection thứ hai chỉ thất bại trên native, có thể điều tra riêng proxy hoặc constructor của nó mà không phải xem lại toàn bộ điều kiện lọc. Nếu tích hợp chưa hỗ trợ cách chọn projection động, chuyển hai nhánh sang hợp đồng trả về cụ thể giúp giữ nhu cầu nghiệp vụ rõ ràng trong khi thu hẹp điểm động.

Việc viết rõ các lựa chọn làm cho quá trình build biết nhiều hơn và giúp người bảo trì xác định chính xác những đường phải tiếp tục được kiểm tra khi nâng phiên bản.

## 11. Những ngộ nhận cần tránh

- **“Có AOT là không còn reflection.”** Một số đường vẫn dùng reflection; điều quan trọng là có cơ chế hỗ trợ và metadata phù hợp.
- **“Truyền `SomeDto.class` là chắc chắn đủ.”** Kiểu được tham chiếu không tự chứng minh mọi constructor, proxy và đường mapping đều hợp lệ.
- **“Q-type là mã sinh nên Querydsl tự động chạy native.”** Mã sinh chỉ là một khâu trong chuỗi thực thi truy vấn.
- **“Kotlin chỉ cần all-open và no-arg.”** Hai cơ chế đó không thay thế constructor mapping, nullability hoặc hỗ trợ AOT của thư viện.
- **“Hint có thể sửa mọi giới hạn native.”** Hint mô tả truy cập động được hỗ trợ; nó không bổ sung một năng lực runtime mà thư viện hoặc môi trường chưa có.
- **“Build thành công nghĩa là repository đã được kiểm tra.”** Chỉ những đường thực sự được chạy và đối chiếu kết quả mới có bằng chứng hành vi.
- **“Một module chạy thì module khác cũng chạy.”** Abstraction dùng chung không xóa khác biệt của mapper, query engine và provider.

Khi làm việc với Spring Data Commons trong AOT, hãy giữ tập kiểu cần dùng rõ ràng, phân biệt metadata với khả năng thực thi, và kiểm tra từng đường repository quan trọng trên artifact đích. Dynamic projection, proxy, Querydsl và Kotlin cần được đánh giá theo chính cơ chế mà ứng dụng sử dụng và bộ phiên bản đã chọn.