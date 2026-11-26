# Chi phí exposeMetadata và giới hạn sử dụng metadata trong lời gọi

## 1. Vấn đề trong chương Factory và metadata

Trong Spring Data Commons, repository factory ghép interface, implementation nền tảng và các fragment thành repository proxy. Một fragment dùng lại cho nhiều repository đôi khi cần biết phương thức nào đang được gọi để chọn cấu hình tương ứng. Ví dụ, cùng một thao tác xuất dữ liệu nhưng `ProductRepository` dùng cấu hình `products-v1`, còn `CustomerRepository` dùng cấu hình `customers-v2`.

`exposeMetadata` phục vụ nhu cầu truy cập metadata của lời gọi đó. Bật cơ chế này tạo thêm công việc trong đường thực thi của proxy; vì vậy cần quyết định cả **repository nào thực sự cần bật** và **đoạn mã nào được phép phụ thuộc vào ngữ cảnh lời gọi**. Javadoc của factory mô tả việc expose qua `ThreadLocal` và giá trị mặc định `false` để tránh interception bổ sung. [RepositoryFactoryBeanSupport.setExposeMetadata](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/core/support/RepositoryFactoryBeanSupport.html#setExposeMetadata(boolean)).

Bài học thuộc module `SPRING_DATA_COMMONS`, tập trung vào abstraction dùng chung. Metadata hỗ trợ mở rộng repository; khả năng chạy truy vấn, phân trang, sắp xếp, projection, Query by Example và auditing vẫn phải được triển khai theo kho dữ liệu tương ứng. Bật metadata không phải cách bổ sung các tính năng còn thiếu của một store.

Sau bài này, người học cần giải thích được chi phí trên từng lời gọi, chọn cách bật có phạm vi nhỏ và xử lý đúng khi công việc rời khỏi lời gọi repository hiện tại.

## 2. Phân biệt metadata cấu trúc với ngữ cảnh lời gọi

Từ “metadata” có thể chỉ nhiều đối tượng khác nhau:

| Thành phần | Câu hỏi nó giúp trả lời | Cách sử dụng phù hợp |
| --- | --- | --- |
| `RepositoryMetadata` | Repository quản lý domain type, ID type và interface nào? | Cấu hình, phân tích cấu trúc repository |
| `RepositoryInformation` | Phương thức thuộc truy vấn, base class hay phần mở rộng nào? | Tích hợp với quá trình tạo và định tuyến repository |
| `RepositoryMethodContext` | Phương thức repository nào đang được gọi trong ngữ cảnh hiện tại? | Fragment hoặc hạ tầng cần quyết định theo lời gọi |
| Metadata mapping của store | Entity liên hệ với bảng, collection, thuộc tính hay identifier thế nào? | Sử dụng mapping abstraction đúng store |

`RepositoryMetadata` cung cấp thông tin về interface và các kiểu repository quản lý. `RepositoryInformation` mở rộng abstraction đó bằng thông tin phục vụ phân loại và tìm phương thức đích. Hai đối tượng này mô tả cấu trúc, khác với câu hỏi “lời gọi nào đang diễn ra?”. [RepositoryMetadata](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/core/RepositoryMetadata.html), [RepositoryInformation](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/core/RepositoryInformation.html).

Ví dụ, việc một repository quản lý `Product` là thông tin cấu trúc. Việc thread hiện tại đang chạy phương thức `export(String)` trên repository là thông tin của lời gọi. Một thư viện chỉ cần loại domain để khởi tạo adapter nên xem xét nhận loại domain qua constructor hoặc cấu hình trước khi chọn truy cập ngữ cảnh động.

Không dùng domain type để suy trực tiếp tên bảng hoặc index. Quy ước đặt tên, annotation mapping và cấu hình triển khai có thể tạo ra tên hoàn toàn khác tên lớp. Tương tự, domain type của repository không đủ để xác định kiểu projection mà một phương thức cụ thể trả về.

## 3. Hợp đồng truy cập RepositoryMethodContext

API truy cập thường có dạng:

```java
import java.lang.reflect.Method;
import org.springframework.data.repository.core.RepositoryMethodContext;

RepositoryMethodContext context = RepositoryMethodContext.getContext();
Method invokedMethod = context.getMethod();
```

`getContext()` trả về context hoặc ném `IllegalStateException` khi không tìm thấy metadata của lời gọi; đây không phải API trả `null` để báo “không có context”. Đối tượng `Method` biểu diễn phương thức được gọi trên interface repository, có thể khác phương thức implementation nhận việc sau khi proxy định tuyến. [RepositoryMethodContext](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/core/RepositoryMethodContext.html).

Có ba điều cần kiểm tra khi thiết kế đoạn mã phụ thuộc context:

1. Repository thực tế đã được cấu hình để expose metadata.
2. Đường gọi đang đi qua repository proxy và đã vào phần thực thi có ngữ cảnh này.
3. Việc đọc diễn ra trong phạm vi thực thi hiện tại, trước khi ngữ cảnh bị kết thúc hoặc bị thay bởi một lời gọi khác.

Việc một đối tượng là Spring bean, đang có transaction hoặc đang xử lý HTTP request không thay thế các điều kiện trên. Một helper đồng bộ được fragment gọi trong cùng thread có thể đọc context, nhưng khi helper được gọi từ một đường khác thì tiền điều kiện ấy không còn chắc chắn. Truyền tham số cho helper thường làm hợp đồng rõ hơn.

Các ví dụ trong bài dùng `getMethod()` để tập trung vào ranh giới lời gọi. Khi cần lấy thêm repository metadata từ context, dùng accessor theo Javadoc của phiên bản dependency thực tế; tránh trộn chữ ký API của các dòng phát hành khác nhau.

## 4. Chi phí của exposeMetadata nằm ở đâu?

Không nên hình dung `exposeMetadata` chỉ là một cờ cho phép đọc một object đã có sẵn mà không tác động đường gọi. Khi metadata được expose, hạ tầng cần thêm interception và quản lý ngữ cảnh. Có thể phân tích chi phí theo các nhóm sau:

| Nhóm công việc | Ý nghĩa đối với ứng dụng |
| --- | --- |
| Đi qua hạ tầng expose metadata | Tăng công việc trong đường gọi proxy được áp dụng cơ chế này |
| Thiết lập và kết thúc ngữ cảnh gắn với thread | Bổ sung thao tác quanh phần thực thi repository |
| Đọc context trong fragment | Thêm công việc tại điểm tiêu thụ metadata |
| Reflection hoặc phân tích annotation do ứng dụng viết | Có thể lặp nhiều lần nếu đặt trong mọi lời gọi |
| Tạo khóa, chuyển đổi chuỗi, ghi log do ứng dụng viết | Có thể tốn hơn chính việc lấy context |

Đây là mô hình phân tích, không phải cam kết rằng framework luôn cấp phát một số lượng object cố định hoặc dùng cùng một chuỗi interceptor ở mọi phiên bản. Chi phí thực tế phụ thuộc phiên bản, JVM, cấu hình proxy và logic trong fragment.

Với một đường gọi đồng bộ, có thể dùng mô hình tư duy:

```text
Tổng thời gian quan sát
  ≈ proxy và advice liên quan
  + quản lý ngữ cảnh metadata
  + logic fragment và phân tích metadata
  + thao tác với store hoặc dịch vụ bên ngoài
```

Bật metadata trên một repository là quyết định ở cấp cấu hình proxy. Nó không có nghĩa chi phí chỉ xuất hiện đúng tại câu lệnh `getContext()`. Chỉ thêm điều kiện `if` quanh câu lệnh đọc không loại bỏ phần việc của hạ tầng đã được bật.

Không có một tỷ lệ phần trăm chung cho mọi dự án. Khi thao tác store chậm, phần tăng của proxy có thể khó nhìn thấy trong tổng thời gian. Với một fragment trả dữ liệu nhanh, cache hit hoặc lưu lượng gọi lớn, phần công việc bổ sung dễ đáng chú ý hơn. Hai nhận định này cần được kiểm chứng trong workload thực tế, thay vì chuyển thành khẳng định “luôn rẻ” hoặc “luôn gây chậm đáng kể”.

## 5. Bật metadata cho đúng repository

### 5.1. Marker trên implementation của fragment

Khi fragment thực sự cần đọc ngữ cảnh lời gọi, implementation có thể triển khai marker `RepositoryMetadataAccess`:

```java
import org.springframework.data.repository.core.support.RepositoryMetadataAccess;

public class ProfiledExportImpl
        implements ProfiledExport, RepositoryMetadataAccess {
    // Phần triển khai đầy đủ ở mục 6.
}
```

Marker này diễn đạt nhu cầu ở fragment implementation. Repository composition chứa fragment đó sẽ được bật khả năng expose metadata. Nên đặt marker ở implementation, giữ interface nghiệp vụ của fragment tập trung vào hành vi được cung cấp. [RepositoryMetadataAccess](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/core/support/RepositoryMetadataAccess.html).

Phạm vi ảnh hưởng vẫn là repository proxy sử dụng composition đó. Nếu mười repository cùng sử dụng fragment có marker, hãy tính cả mười repository trong phạm vi đánh giá chi phí; đừng hiểu marker như một cơ chế chỉ bật riêng một dòng code bên trong fragment.

### 5.2. Cấu hình factory có điều kiện

Khi việc bật được quản lý ở lớp cấu hình, có thể dùng `BeanPostProcessor` trước khi repository factory bean được khởi tạo. Ví dụ sau chọn đúng interface repository trong tình huống minh họa:

```java
import org.springframework.beans.factory.config.BeanPostProcessor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.repository.core.support.RepositoryFactoryBeanSupport;

@Configuration(proxyBeanMethods = false)
public class RepositoryMetadataConfiguration {

    @Bean
    static BeanPostProcessor productMetadataExposure() {
        return new BeanPostProcessor() {
            @Override
            public Object postProcessBeforeInitialization(
                    Object bean, String beanName) {

                if (bean instanceof RepositoryFactoryBeanSupport<?, ?, ?> factory
                        && ProductRepository.class.equals(factory.getObjectType())) {
                    factory.setExposeMetadata(true);
                }

                return bean;
            }
        };
    }
}
```

Đây là phương án thay thế cho việc khai báo nhu cầu bằng marker, không phải bước bắt buộc phải thêm sau marker. Điều kiện chọn repository thuộc thiết kế ứng dụng; ví dụ dùng so sánh interface chính xác để tránh vô tình mở rộng phạm vi.

Tài liệu Spring Data cũng minh họa cách bật cờ bằng post-processor và lưu ý việc bật cho mọi factory có thể quá rộng. Cấu hình phải có hiệu lực trong quá trình tạo repository; đừng xem setter như một công tắc có thể bật tắt tùy request trên proxy đang chạy. [Custom Repository Implementations](https://docs.spring.io/spring-data/commons/reference/repositories/custom-implementations.html).

## 6. Ví dụ: fragment chọn cấu hình xuất dữ liệu theo phương thức

Giả sử hệ thống có một backend xuất dữ liệu nhận tên cấu hình xuất và bộ lọc. Annotation trên phương thức repository chọn cấu hình cần dùng. Đây là tình huống minh họa việc đọc metadata trong fragment; backend và mapping của `Product` là phần do ứng dụng cung cấp.

Mỗi kiểu `public` dưới đây đặt trong file Java riêng trong một dự án thực hành. Các đoạn mã chỉ mô tả thiết kế, không tạo thêm file trong bài học này.

### 6.1. Hợp đồng ứng dụng

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
public @interface ExportProfile {
    String value();
}
```

```java
public record ExportReceipt(String profile, String reference) {}
```

```java
public interface ExportBackend {
    ExportReceipt export(String profile, String filter);
}
```

```java
public interface ProfiledExport {
    ExportReceipt export(String filter);
}
```

`ExportBackend` cần có implementation được đăng ký làm bean. Tên profile phải được backend kiểm tra theo cấu hình được phép; annotation không thay thế việc kiểm tra quyền hay kiểm tra bộ lọc đầu vào.

### 6.2. Fragment đọc context ở đầu lời gọi

```java
import java.lang.reflect.Method;
import org.springframework.data.repository.core.RepositoryMethodContext;
import org.springframework.data.repository.core.support.RepositoryMetadataAccess;

public class ProfiledExportImpl
        implements ProfiledExport, RepositoryMetadataAccess {

    private final ExportBackend backend;

    public ProfiledExportImpl(ExportBackend backend) {
        this.backend = backend;
    }

    @Override
    public ExportReceipt export(String filter) {
        Method method = RepositoryMethodContext.getContext().getMethod();
        ExportProfile annotation = method.getAnnotation(ExportProfile.class);

        if (annotation == null || annotation.value().isBlank()) {
            throw new IllegalStateException(
                    "Missing @ExportProfile on " + method.toGenericString());
        }

        String profile = annotation.value();
        return backend.export(profile, filter);
    }
}
```

Sau khi lấy chuỗi `profile`, fragment truyền giá trị đó xuống backend. Backend không cần biết `RepositoryMethodContext`, nên có thể được gọi và kiểm thử độc lập bằng tham số bình thường.

Ví dụ dùng `getAnnotation()` trực tiếp và cố ý yêu cầu annotation nằm ngay trên phương thức được gọi. Nó không cài đặt tìm annotation tổng hợp, meta-annotation hay chính sách tìm kiếm qua mọi interface cha. Nếu sản phẩm cần các quy tắc đó, hãy thiết kế riêng thay vì giả định reflection đơn giản đã bao phủ.

### 6.3. Repository công bố phương thức có cấu hình

```java
import org.springframework.data.repository.CrudRepository;

public interface ProductRepository
        extends CrudRepository<Product, Long>, ProfiledExport {

    @Override
    @ExportProfile("products-v1")
    ExportReceipt export(String filter);
}
```

Đặt `ProfiledExportImpl` tại vị trí phù hợp với cơ chế phát hiện fragment của ứng dụng, theo quy ước tên fragment cộng hậu tố `Impl`. Ứng dụng cần module Spring Data của store để tạo `ProductRepository`, mapping hợp lệ cho `Product` và bean `ExportBackend`.

Khi service gọi `productRepository.export("active=true")` qua repository proxy đã cấu hình, fragment lấy profile từ phương thức interface rồi chuyển tiếp sang backend. Nếu tạo `new ProfiledExportImpl(backend)` và gọi trực tiếp từ một luồng kiểm thử độc lập, marker không tự tạo proxy hay context cho đối tượng đó.

Nếu mỗi implementation luôn gắn cố định với một profile, constructor nhận `String profile` có thể đơn giản hơn toàn bộ cơ chế trên. Giá trị của metadata động xuất hiện khi cùng implementation cần thay đổi cách xử lý theo repository method thực tế.

## 7. Ranh giới thời gian và thread

### 7.1. Ngữ cảnh của lời gọi không phải ngữ cảnh của request

Có thể hình dung lời gọi đồng bộ như sau:

```text
Service
  -> repository proxy có expose metadata
     -> thiết lập ngữ cảnh cho lời gọi
        -> fragment đọc metadata
        -> helper đồng bộ hoặc backend nhận tham số đã trích xuất
     -> kết thúc ngữ cảnh của lời gọi
  <- kết quả về Service
```

Đây là sơ đồ khái niệm, không mô tả thứ tự tuyệt đối giữa mọi transaction advice, security advice và interceptor tùy biến.

Không để controller hoặc service lấy context sau khi repository đã trả về:

```java
ExportReceipt receipt = productRepository.export("active=true");

// Sai hợp đồng: lời gọi export đã kết thúc tại đây.
RepositoryMethodContext.getContext();
```

Ở đường gọi ngoài cùng không có một ngữ cảnh repository khác bao quanh, việc đọc này không còn context của `export`. Nếu đang ở trong một lời gọi repository lồng nhau, context quan sát được còn có thể thuộc phạm vi bao ngoài. Vì vậy không sử dụng nó để suy ngược một thao tác đã hoàn tất.

### 7.2. Công việc được gửi sang executor

Đoạn mã dưới đây đặt việc đọc context vào công việc có thể chạy trên thread khác và sau khi proxy đã trả về:

```java
executor.execute(() -> {
    RepositoryMethodContext context = RepositoryMethodContext.getContext();
    // Không có hợp đồng tự truyền context từ thread gọi repository.
});
```

Thay vào đó, trích xuất dữ liệu cần thiết khi còn ở trong fragment rồi truyền tường minh:

```java
// Các dòng này chạy bên trong fragment, trong lời gọi repository hiện tại.
Method method = RepositoryMethodContext.getContext().getMethod();
ExportProfile annotation = method.getAnnotation(ExportProfile.class);
if (annotation == null) {
    throw new IllegalStateException("Export profile is required");
}

String profile = annotation.value();
String submittedFilter = filter;
executor.execute(() -> backend.export(profile, submittedFilter));
```

`executor`, `backend` và `filter` ở đây là các dependency hoặc tham số của fragment. Đoạn mã minh họa việc truyền dữ liệu, chưa bao gồm hợp đồng tiếp nhận tác vụ, xử lý lỗi và trả kết quả cho một API xuất dữ liệu bất đồng bộ.

Không tự sao chép `ThreadLocal` nội bộ hoặc giữ nguyên context để giả lập một lời gọi repository trên worker thread. Chọn DTO nhỏ chỉ gồm dữ liệu cần thiết. Nếu công việc bất đồng bộ cần transaction, quyền truy cập hoặc thông tin người dùng, từng nhu cầu đó phải có hợp đồng riêng; chuỗi `profile` không mang theo chúng.

### 7.3. Reactive và xử lý trì hoãn

Một phương thức trả `Mono`, `Flux`, `Stream` hoặc callback có thể hoàn tất việc tạo đối tượng kết quả trước khi công việc thật sự chạy. Việc tạo pipeline trong lời gọi repository không chứng minh callback sau đó vẫn có context.

Ví dụ nên tránh phụ thuộc:

```java
return Mono.defer(() -> {
    Method method = RepositoryMethodContext.getContext().getMethod();
    return reactiveBackend.export(method.getName(), filter);
});
```

Nếu phiên bản và đường gọi đang dùng cho phép đọc context trong phần đồng bộ của fragment, hãy đọc tại đó và capture giá trị cần thiết trước khi tạo callback. Không suy rằng Reactor Context, transaction reactive hay cơ chế đổi scheduler sẽ tự truyền `RepositoryMethodContext`. Khi thiết kế không bảo đảm điểm đọc đồng bộ, nhận cấu hình bằng tham số hoặc dependency là phương án rõ ràng hơn.

## 8. Những gì metadata trong lời gọi không cung cấp

| Mong muốn | Vì sao exposeMetadata chưa đủ | Hướng xử lý |
| --- | --- | --- |
| Lấy đối số đang được truyền vào phương thức | `RepositoryMethodContext` không cung cấp API danh sách argument | Dùng tham số của fragment hoặc thiết kế interceptor riêng |
| Lấy SQL hay query đã biên dịch | Thông tin về interface/method không phải kế hoạch thực thi | Dùng cơ chế quan sát và API của store |
| Xác định tên bảng, collection hoặc index | Repository metadata và mapping có vai trò khác nhau | Dùng mapping metadata hoặc cấu hình tường minh |
| Bật derived query hay Query by Example cho store bất kỳ | Metadata không tạo bộ thực thi truy vấn | Kiểm tra abstraction và khả năng module store hỗ trợ |
| Xác định tenant hoặc người thực hiện auditing | Method metadata không đại diện danh tính runtime | Dùng hợp đồng tenant/security và auditing phù hợp |
| Bảo đảm transaction hoặc locking | Expose metadata chỉ hỗ trợ truy cập metadata lời gọi | Cấu hình transaction, locking theo store |

Một `Method` phản chiếu có thể cho biết khai báo tham số, nhưng khai báo khác với giá trị đối số của lần gọi. Tương tự, tên `findByStatus` gợi ý ý định của derived query nhưng không cho phép suy chính xác mọi chi tiết truy vấn, phân trang, projection hoặc chiến lược fetch.

Nếu cần phân biệt hai phương thức overload, tên phương thức đơn lẻ là không đủ. Nếu cùng fragment interface được ghép vào nhiều repository, lớp khai báo `Method` cũng chưa chắc đủ làm khóa định danh repository cụ thể. Thiết kế cache hoặc nhãn theo đúng dữ liệu thực sự cần phân biệt.

## 9. Cache và trạng thái dùng chung

Giả sử reflection để tìm annotation đã xuất hiện trong hồ sơ hiệu năng. Có thể cân nhắc cache kết quả cấu hình ổn định thay vì phân tích lại ở mọi lời gọi. Tuy nhiên, cần phân biệt:

- **Có thể cân nhắc cache:** profile đã kiểm tra, descriptor bất biến, kết quả phân tích cấu trúc method.
- **Không nên lưu làm trạng thái dùng chung:** context hiện tại, tham số người dùng, tenant hiện tại hoặc dữ liệu nhạy cảm của lần gọi.

Không gán `RepositoryMethodContext.getContext()` vào field của singleton fragment để dùng lại. Field đó có thể bị nhiều thread cập nhật đồng thời, hoặc trỏ đến một lời gọi đã kết thúc. Dùng local variable và truyền giá trị cần thiết xuống các tầng sau.

Khóa cache phải phản ánh các đầu vào tạo nên kết quả. Với annotation trực tiếp trên `Method`, kết quả tra cứu có thể chỉ phụ thuộc method. Nếu quy tắc còn phụ thuộc repository cụ thể hoặc cấu hình theo store, phải đưa các yếu tố đó vào thiết kế khóa hoặc tách cache theo phạm vi phù hợp. Khi có thay đổi cấu hình động, cần xác định cả chính sách làm mới.

Cache tối ưu phần phân tích do ứng dụng thêm vào; nó không tự gỡ chi phí expose metadata trên proxy. Đừng triển khai cache chỉ vì “reflection có vẻ chậm” khi chưa thấy nó là điểm đáng tối ưu.

## 10. Đánh giá chi phí trong dự án thực tế

Để đánh giá riêng phần expose metadata, so sánh hai cấu hình có cùng đường gọi không cần đọc context: một cấu hình không bật và một cấu hình bật. Sau đó đánh giá toàn bộ tính năng fragment, bao gồm đọc context và phân tích annotation.

Không tắt metadata trên fragment vốn bắt buộc gọi `getContext()` rồi dùng lỗi nhận được làm mẫu đo đối chứng. Hai nhánh phải cùng thực hiện được chức năng mà phép đo muốn so sánh.

Một kế hoạch đo có thể gồm:

1. Chọn repository và thao tác đại diện, giữ cùng JVM, dữ liệu và mức đồng thời.
2. Đo đường gọi nhẹ với backend giả để quan sát phần việc quanh proxy.
3. Đo lại với store thật để biết ảnh hưởng đối với workload sản phẩm.
4. Quan sát throughput, độ trễ phân vị, CPU và lượng cấp phát thay vì chỉ nhìn thời gian trung bình.
5. Tách logging và công việc phụ khỏi phép đo, hoặc bảo đảm chúng tương đương giữa hai nhánh.

Đây là hướng dẫn thực hành, không phải kết quả benchmark. Không thể suy ra một con số nanosecond hay mức suy giảm phần trăm cho dự án chỉ từ việc có thêm `ThreadLocal`.

## 11. Chẩn đoán lỗi theo tiền điều kiện

| Hiện tượng | Điều cần kiểm tra trước |
| --- | --- |
| `getContext()` ném `IllegalStateException` trong fragment | Marker đã nằm trên implementation được ghép thật sự chưa; factory đã được cấu hình trước khi tạo repository chưa? |
| Gọi repository hoạt động nhưng gọi implementation trực tiếp bị lỗi | Đường trực tiếp có bỏ qua proxy và ngữ cảnh lời gọi không? |
| Chạy đồng bộ được, chạy executor hoặc callback thì lỗi | Việc đọc có xảy ra sau khi rời phạm vi lời gọi hoặc trên thread khác không? |
| Không tìm được `@ExportProfile` | Annotation có nằm trực tiếp trên phương thức interface được gọi, và có retention runtime không? |
| Repository không liên quan cũng chịu chi phí | Post-processor có chọn mọi factory hoặc fragment có marker được dùng rộng hơn dự kiến không? |
| Export lấy nhầm cấu hình khi có nhiều repository | Có lưu metadata vào field dùng chung hoặc tạo khóa cache thiếu repository không? |

Không bắt mọi `IllegalStateException` rồi âm thầm chọn profile mặc định. Nếu metadata là bắt buộc, thiếu context hoặc cấu hình phải được báo rõ; nếu nó là tùy chọn, thiết kế một đường gọi không phụ thuộc context với hành vi được mô tả cụ thể.

Với ví dụ ở mục 6, một đợt kiểm chứng tích hợp sau này có thể kiểm tra: gọi qua proxy đọc đúng profile; thiếu annotation báo lỗi; gọi trực tiếp fragment từ ngoài ngữ cảnh báo lỗi; backend nhận đúng chuỗi profile mà không phải đọc context. Các tình huống này kiểm tra hợp đồng sử dụng, không thay thế đánh giá hiệu năng.

## 12. Quy tắc áp dụng

Chọn constructor hoặc cấu hình tĩnh khi thông tin đã biết trước và không đổi theo lời gọi. Chọn marker trên fragment khi nhu cầu đọc metadata thuộc về fragment đó; dùng cấu hình factory có điều kiện khi ứng dụng cần quản lý phạm vi bật ở lớp hạ tầng.

Trong phần thực thi repository, đọc context tại điểm cần thiết rồi chuyển thành dữ liệu nhỏ, rõ nghĩa. Giữ backend và logic xử lý phía sau phụ thuộc vào tham số tường minh. Đối với async, reactive hoặc kết quả trì hoãn, thiết kế việc truyền dữ liệu riêng thay vì dựa vào sự tồn tại ngẫu nhiên của ngữ cảnh gắn với thread.

Quyết định bật `exposeMetadata` nên gắn với một nhu cầu mở rộng repository cụ thể, một phạm vi proxy xác định và một cách kiểm chứng phù hợp. Như vậy ứng dụng sử dụng được metadata của Spring Data Commons mà vẫn giữ đúng ranh giới của lời gọi và khả năng riêng của từng kho dữ liệu.
