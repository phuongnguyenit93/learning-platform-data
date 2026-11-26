# Đóng gói fragment dùng chung ngoài package quét theo phiên bản hỗ trợ

## 1. Bài toán: fragment có trong dependency nhưng repository chưa được ghép

Trong Spring Data Commons, repository có thể được tạo bằng cách kết hợp các interface và các phần cài đặt gọi là **repository fragment**. Cách tổ chức này giúp một repository vừa sử dụng CRUD hoặc derived query do kho dữ liệu cung cấp, vừa có thêm hành vi do ứng dụng tự định nghĩa.

Khi phát triển trong một ứng dụng, interface fragment và implementation thường nằm gần package chứa repository. Nhưng khi đưa chức năng dùng chung vào một JAR, implementation có thể nằm ngoài phạm vi phát hiện implementation của cấu hình repository.

Ví dụ:

```text
shared-search.jar
└── com.acme.shared.search
    ├── ExternalSearch
    ├── DefaultExternalSearch
    └── ExternalSearchGateway

shop-application
└── com.shop
    ├── ShopApplication
    ├── domain.Product
    └── persistence.ProductRepository
```

Ứng dụng chỉ cấu hình repository trong `com.shop.persistence`. Việc thêm `shared-search.jar` vào classpath không tự bảo đảm rằng `DefaultExternalSearch` sẽ trở thành một phần của `ProductRepository`.

Mục tiêu của bài là đóng gói contract, implementation và thông tin đăng ký để một fragment có thể được dùng lại ở nhiều ứng dụng. Cách đăng ký phải phù hợp với phiên bản Spring Data thực tế đang chạy.

## 2. Phân biệt ba cơ chế phát hiện

| Cơ chế | Đối tượng được tìm hoặc đăng ký | Ý nghĩa đối với fragment |
| --- | --- | --- |
| Component scanning của Spring | Bean được đánh dấu hoặc khai báo trong application context | Giúp tạo bean và giải quyết dependency; không nên coi đây là bằng chứng repository đã được ghép fragment |
| Repository scanning của từng module Spring Data | Repository interface và các ứng viên implementation theo quy tắc của module | Quyết định repository nào được tạo và hỗ trợ phát hiện implementation theo quy ước |
| Đăng ký fragment qua `META-INF/spring.factories` khi phiên bản hỗ trợ | Ánh xạ interface fragment sang lớp implementation | Cho phép thư viện công bố implementation dù package của nó nằm ngoài phạm vi phát hiện thông thường |

Hai sự kiện sau khác nhau:

1. Application context có một bean `DefaultExternalSearch`.
2. Proxy `ProductRepository` đã được ghép với implementation đó.

Một dependency đã được inject thành công chưa chứng minh rằng phương thức fragment đã được nối vào proxy repository. Cần gọi phương thức đó qua chính repository để kiểm chứng.

Cũng cần phân biệt **fragment riêng cho một nhóm repository** với **base repository class**. Fragment phù hợp khi các repository chủ động chọn một năng lực bằng cách kế thừa interface tương ứng. Thay base class là thay đổi cơ chế nền của các repository thuộc cấu hình áp dụng, thường phụ thuộc module như JPA hoặc MongoDB.

## 3. Chọn cơ chế theo phiên bản thực tế

### 3.1. Kiểm tra Spring Data Commons, không chỉ tên Spring Boot

Spring Boot thường quản lý các dependency Spring Data thông qua một bộ phiên bản tương thích. Tuy nhiên, ứng dụng có thể đã override một phần dependency hoặc sử dụng một release train khác.

Trước khi áp dụng đăng ký ngoài package quét, cần xác định:

- Phiên bản Spring Data Commons thực tế được resolve.
- Phiên bản module tạo repository, chẳng hạn Spring Data JPA hoặc Spring Data MongoDB.
- Tài liệu repository customization của đúng nhánh phiên bản có mô tả đăng ký fragment qua `META-INF/spring.factories` hay không.
- Bộ dependency của ứng dụng có đồng bộ theo BOM hoặc release train được sử dụng hay không.

Không lấy tài liệu của nhánh mới nhất làm bằng chứng rằng một ứng dụng chạy phiên bản cũ cũng hỗ trợ cùng cơ chế. Việc Spring Framework có lớp `SpringFactoriesLoader` cũng chưa đủ: hạ tầng repository của phiên bản đang dùng phải thực sự sử dụng ánh xạ fragment này.

### 3.2. Ma trận lựa chọn

| Tình trạng phiên bản | Cách triển khai |
| --- | --- |
| Đã xác nhận có hỗ trợ đăng ký fragment qua `spring.factories` | Đóng gói ánh xạ interface → implementation trong JAR dùng chung |
| Hỗ trợ fragment theo quy ước nhưng chưa hỗ trợ ánh xạ ngoài package quét | Tạo một fragment bridge mỏng trong package ứng dụng được phát hiện |
| Chưa xác định khả năng hỗ trợ | Xác định dependency đã resolve và thử integration tối thiểu trước khi chọn cơ chế |
| Commons và module kho dữ liệu lệch bộ phiên bản | Đồng bộ dependency trước; không giải quyết bằng cách mở rộng package scan tùy tiện |

Các ví dụ `spring.factories` bên dưới dành cho phiên bản đã xác nhận có hỗ trợ cơ chế đó. Phần bridge cung cấp một cách thích nghi cho phiên bản hỗ trợ mô hình fragment nhưng chưa có đường đăng ký này.

Nếu thư viện được phát hành cho nhiều dòng ứng dụng, nên công bố rõ phiên bản Spring Data đã kiểm chứng và duy trì ứng dụng mẫu tương ứng. Chỉ ghi “hỗ trợ Spring Boot” là chưa đủ để diễn đạt điều kiện tương thích.

## 4. Thiết kế fragment dùng chung

Ví dụ sau bổ sung tìm kiếm qua một hệ thống chỉ mục bên ngoài. Fragment nhận rõ kiểu kết quả để tránh phải dựa vào API metadata repository có thể khác nhau theo phiên bản.

### 4.1. Interface fragment

File minh họa `ExternalSearch.java`:

```java
package com.acme.shared.search;

import java.util.List;

public interface ExternalSearch<T> {

    List<T> searchExternal(
            Class<T> resultType,
            String phrase,
            int maxResults);
}
```

Interface này không kế thừa `Repository`. Nó mô tả một năng lực để các repository khác chọn dùng.

Một fragment chỉ chứa phương thức nghiệp vụ như trên cũng không cần `@NoRepositoryBean`. Annotation đó hữu ích khi thiết kế interface trung gian thuộc hệ phân cấp Spring Data repository và cần ngăn tạo repository trực tiếp từ interface trung gian ấy.

### 4.2. Contract kết nối tới hệ thống bên ngoài

File minh họa `ExternalSearchGateway.java`:

```java
package com.acme.shared.search;

import java.util.List;

public interface ExternalSearchGateway {

    <T> List<T> search(
            Class<T> resultType,
            String phrase,
            int maxResults);
}
```

Gateway che giấu chi tiết client, giao thức truy cập, tên chỉ mục và cách ánh xạ kết quả. Ứng dụng cung cấp một bean triển khai gateway theo hệ thống thực tế.

Đây là ranh giới giữa hành vi dùng chung và hạ tầng cụ thể. Một thư viện fragment không nên tự giả định mọi ứng dụng đều có `EntityManager`, `MongoTemplate` hoặc cùng một cơ chế giao dịch.

### 4.3. Implementation

File minh họa `DefaultExternalSearch.java`:

```java
package com.acme.shared.search;

import java.util.List;
import java.util.Objects;

public class DefaultExternalSearch<T> implements ExternalSearch<T> {

    private final ExternalSearchGateway gateway;

    public DefaultExternalSearch(ExternalSearchGateway gateway) {
        this.gateway = Objects.requireNonNull(gateway, "gateway");
    }

    @Override
    public List<T> searchExternal(
            Class<T> resultType,
            String phrase,
            int maxResults) {

        Objects.requireNonNull(resultType, "resultType");

        if (phrase == null || phrase.trim().isEmpty()) {
            throw new IllegalArgumentException(
                    "phrase must not be blank");
        }

        if (maxResults < 1 || maxResults > 100) {
            throw new IllegalArgumentException(
                    "maxResults must be between 1 and 100");
        }

        return gateway.search(
                resultType,
                phrase.trim(),
                maxResults);
    }
}
```

Implementation dùng constructor injection. Trong cấu hình ánh xạ được hỗ trợ, hạ tầng Spring Data tìm implementation và tích hợp việc tạo bean với Spring container; dependency `ExternalSearchGateway` vẫn phải được ứng dụng cung cấp.

Không thêm `@Component` chỉ để mong repository tự nhận fragment. Ví dụ chọn đăng ký qua metadata của JAR và không dựa vào việc quét stereotype của package thư viện.

Lớp trên không giữ `Class<T>` trong một field có thể thay đổi theo mỗi lần gọi. Điều này tránh gắn trạng thái riêng của một repository vào instance dùng chung. Nếu bổ sung cache hoặc client có trạng thái, phải xem xét thread safety và vòng đời bean.

## 5. Đăng ký implementation từ JAR ngoài package quét

### 5.1. Nội dung tài nguyên đăng ký

Trong project thư viện, tạo tài nguyên:

```text
src/main/resources/META-INF/spring.factories
```

Nội dung:

```properties
com.acme.shared.search.ExternalSearch=com.acme.shared.search.DefaultExternalSearch
```

Ở cơ chế đăng ký fragment này:

- **Key** là tên đầy đủ, gồm package, của interface fragment.
- **Value** là tên đầy đủ, gồm package, của lớp implementation.
- Không ghi tham số generic như `<T>` vào key hoặc value.
- Không đặt key thành tên repository của từng ứng dụng.
- Đường dẫn và tên tài nguyên phải đúng, kể cả chữ hoa trong `META-INF`.

Mapping gắn với contract dùng chung, nên thư viện không phải biết trước `ProductRepository`, `CustomerRepository` hoặc package của ứng dụng sử dụng nó.

### 5.2. Trạng thái sau khi đóng gói

JAR cuối cùng cần có cấu trúc tương đương:

```text
shared-search.jar
├── META-INF/
│   └── spring.factories
└── com/acme/shared/search/
    ├── ExternalSearch.class
    ├── DefaultExternalSearch.class
    └── ExternalSearchGateway.class
```

Nếu dùng shaded JAR hoặc quy trình gộp nhiều thư viện, phải kiểm tra bước đóng gói có giữ và gộp tài nguyên `spring.factories` đúng cách hay không. Hai thư viện cùng chứa một tài nguyên cùng đường dẫn có thể bị công cụ đóng gói xử lý theo cách làm mất một phần đăng ký.

Khi nhiều JAR cùng công bố implementation cho một fragment interface, không nên dựa vào thứ tự classpath để chọn hành vi. Hãy làm rõ chính sách chọn implementation, tách contract hoặc dùng bridge cấu hình tường minh.

### 5.3. Khác với đăng ký auto-configuration

Không thay mapping trên bằng:

```properties
org.springframework.boot.autoconfigure.EnableAutoConfiguration=...
```

Đó là một loại đăng ký khác, không có nghĩa “ghép implementation này vào fragment interface này”.

Tương tự, tài nguyên `AutoConfiguration.imports` phục vụ auto-configuration của Spring Boot không thay thế trực tiếp ánh xạ fragment. Một thư viện có thể cần cả hai cơ chế cho hai mục đích riêng:

- Metadata fragment giúp hạ tầng repository tìm implementation.
- Auto-configuration hoặc cấu hình ứng dụng có thể cung cấp gateway, client và các bean phụ thuộc.

Cú pháp và yêu cầu của auto-configuration phải được chọn theo phiên bản Spring Boot tương ứng, độc lập với việc xác nhận hỗ trợ fragment.

## 6. Sử dụng fragment trong ứng dụng

Phần này minh họa tích hợp với Spring Data JPA. JPA chỉ là module tạo repository trong ví dụ; cơ chế composition được chia sẻ qua Spring Data Commons.

### 6.1. Cấu hình package repository

```java
package com.shop;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;

@Configuration
@EnableJpaRepositories(basePackages = "com.shop.persistence")
public class JpaRepositoryConfiguration {
}
```

Ứng dụng còn cần cấu hình JPA thông thường, gồm entity, datasource và transaction manager phù hợp. Ví dụ không trình bày toàn bộ bootstrap JPA.

Trong một ứng dụng Spring Boot đã tự cấu hình đúng package repository, thường không cần thêm cấu hình thủ công chỉ để dùng fragment. Khai báo trên giúp nhìn rõ ranh giới package trong bài học.

### 6.2. Repository chọn dùng fragment

Giả sử `Product` là entity JPA hợp lệ có khóa kiểu `Long`:

```java
package com.shop.persistence;

import com.acme.shared.search.ExternalSearch;
import com.shop.domain.Product;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ProductRepository
        extends JpaRepository<Product, Long>,
                ExternalSearch<Product> {
}
```

Điểm quyết định là `ProductRepository` kế thừa `ExternalSearch<Product>`.

Chỉ thêm dependency chứa fragment mà không kế thừa interface thì repository không tự có thêm contract tìm kiếm đó.

### 6.3. Cung cấp dependency của implementation

Đoạn sau là gateway giả dùng trong cấu hình kiểm thử, không phải client tìm kiếm production:

```java
package com.shop;

import com.acme.shared.search.ExternalSearchGateway;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.util.Collections;
import java.util.List;

@Configuration
public class SearchStubConfiguration {

    @Bean
    public ExternalSearchGateway externalSearchGateway() {
        return new ExternalSearchGateway() {
            @Override
            public <T> List<T> search(
                    Class<T> resultType,
                    String phrase,
                    int maxResults) {
                return Collections.emptyList();
            }
        };
    }
}
```

Khi triển khai thật, thay gateway giả bằng adapter gọi hệ thống chỉ mục. Nếu có nhiều bean cùng kiểu gateway, cần thiết kế lựa chọn rõ ràng bằng cấu hình phù hợp, thay vì kỳ vọng framework tự biết client nào dành cho fragment.

### 6.4. Gọi qua repository

```java
List<Product> matches = productRepository.searchExternal(
        Product.class,
        "spring data",
        20);
```

Luồng xử lý mong đợi:

```text
ProductRepository proxy
    → fragment ExternalSearch
    → DefaultExternalSearch
    → ExternalSearchGateway bean
    → hệ thống tìm kiếm hoặc gateway giả
```

Các phương thức CRUD và derived query khác vẫn do các phần tương ứng của repository xử lý. Không cần tạo `ProductRepositoryImpl` chỉ để chuyển tiếp một phương thức đã nằm trong fragment được đăng ký đúng.

## 7. Phương án bridge cho phiên bản chưa hỗ trợ mapping

Nếu phiên bản đang dùng có repository fragments theo quy ước nhưng chưa hỗ trợ đăng ký implementation ngoài package qua `spring.factories`, có thể giữ thư viện dùng chung và tạo bridge trong package ứng dụng.

### 7.1. Interface bridge của ứng dụng

```java
package com.shop.persistence;

import com.acme.shared.search.ExternalSearch;
import com.shop.domain.Product;

public interface ProductSearchFragment extends ExternalSearch<Product> {
}
```

### 7.2. Implementation bridge nằm trong phạm vi phát hiện

```java
package com.shop.persistence;

import com.acme.shared.search.DefaultExternalSearch;
import com.acme.shared.search.ExternalSearchGateway;
import com.shop.domain.Product;

public class ProductSearchFragmentImpl
        extends DefaultExternalSearch<Product>
        implements ProductSearchFragment {

    public ProductSearchFragmentImpl(ExternalSearchGateway gateway) {
        super(gateway);
    }
}
```

Bridge không sao chép xử lý tìm kiếm. Nó kế thừa implementation của thư viện và cung cấp một lớp ở vị trí mà cấu hình repository của ứng dụng có thể phát hiện theo quy ước.

Tên `ProductSearchFragmentImpl` ghép từ tên interface fragment `ProductSearchFragment` và postfix mặc định `Impl`. Nếu ứng dụng đã cấu hình postfix khác, tên implementation phải theo cấu hình đó.

### 7.3. Repository kế thừa bridge

```java
package com.shop.persistence;

import com.shop.domain.Product;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ProductRepository
        extends JpaRepository<Product, Long>,
                ProductSearchFragment {
}
```

Đây là cấu hình thay thế cho cách kế thừa trực tiếp `ExternalSearch<Product>` ở phần trước. Chọn một đường ghép rõ ràng cho ứng dụng, tránh đăng ký đồng thời nhiều implementation cạnh tranh cho cùng contract.

Bridge cũng hữu ích khi ứng dụng cần tùy biến constructor hoặc chọn một gateway riêng. Đổi lại, mỗi ứng dụng phải duy trì một lớp thích nghi nhỏ.

Không chuyển sang quy ước implementation gắn với toàn bộ tên repository nếu phiên bản đang dùng đã hỗ trợ composition theo từng fragment và bridge giải quyết được yêu cầu.

## 8. Giữ ranh giới giữa Commons và từng loại kho dữ liệu

Đưa code vào một JAR chung không tự làm cho hành vi tương thích mọi kho dữ liệu.

| Nội dung | Có thể dùng chung ở mức contract | Điều cần xác nhận theo kho dữ liệu |
| --- | --- | --- |
| Interface fragment và kiểm tra tham số | Có | Tên phương thức có xung đột với các fragment khác không |
| Client tìm kiếm ngoài qua gateway | Có thể | Ánh xạ domain type, chỉ mục, quyền truy cập và mô hình thực thi |
| `EntityManager`, JPQL, Criteria JPA | Không phải abstraction trung lập của Commons | Chỉ áp dụng cho ứng dụng JPA tương ứng |
| `MongoTemplate` hoặc truy vấn đặc thù MongoDB | Không phải abstraction trung lập của Commons | Chỉ áp dụng cho cấu hình MongoDB tương ứng |
| Giao dịch và đồng bộ chỉ mục | Không tự có từ composition | Transaction manager, thời điểm cập nhật chỉ mục và cách xử lý lỗi |
| API reactive | Cần contract và implementation riêng phù hợp | Client phải hỗ trợ mô hình reactive, tránh gọi blocking trên luồng không phù hợp |

Ví dụ `ExternalSearch<T>` trả về `List<T>` là API đồng bộ. Không nên ghép nó vào repository reactive rồi mặc định rằng lời gọi đã trở thành non-blocking.

Tương tự, fragment tìm kiếm ngoài không tự biến kết quả thành entity được quản lý bởi persistence context JPA. Nếu cần hành vi đó, adapter hoặc tầng ứng dụng phải xác định cách nạp lại entity và chi phí truy vấn đi kèm.

### Phân trang và sắp xếp cần một contract riêng

Thêm `Pageable` hoặc trả về `Page<T>` không tự khiến hệ thống tìm kiếm ngoài hỗ trợ offset, sort hay tổng số kết quả.

Nếu mở rộng fragment để hỗ trợ các abstraction này, phải quy định rõ:

- Backend hỗ trợ offset pagination, cursor hay search-after.
- Thuộc tính sort nào hợp lệ và cách ánh xạ sang tên trường của chỉ mục.
- Tổng số kết quả là chính xác, ước lượng hay không có.
- Thứ tự có ổn định giữa các trang khi dữ liệu thay đổi hay không.

Có thể dùng `Slice<T>` khi chỉ cần biết còn trang tiếp theo và backend đáp ứng được contract đó. Không tạo một `Page<T>` với tổng số giả chỉ để khớp kiểu trả về.

## 9. Metadata và phạm vi generic

Tên `ExternalSearch<Product>` giúp trình biên dịch kiểm tra kiểu ở code sử dụng. Tuy nhiên, một instance Java của `DefaultExternalSearch<T>` không tự có `Product.class` chỉ nhờ ký hiệu `T`.

Vì thế ví dụ truyền `Class<T>` tường minh:

```java
productRepository.searchExternal(Product.class, "spring", 10);
```

Một thiết kế khác có thể lấy domain type từ metadata repository khi thực thi phương thức. Khi chọn thiết kế đó, cần kiểm tra API metadata của đúng phiên bản, điều kiện bật việc cung cấp metadata và vòng đời của ngữ cảnh gọi. Không giả định metadata luôn sẵn có chỉ vì fragment đã được đăng ký.

Các điểm cần tránh:

- Lấy domain type bằng cách phân tích tên repository.
- Ghi domain type của lần gọi gần nhất vào biến static.
- Dùng chung trạng thái “repository hiện tại” giữa nhiều thread.
- Coi generic type của interface là một cơ chế runtime tự động định tuyến chỉ mục.

Nếu cần ánh xạ `Product.class → products-v2`, hãy đặt mapping trong gateway hoặc một component cấu hình rõ ràng. Không suy ra tên collection, bảng hay index một cách ngầm định nếu mỗi hệ lưu trữ có quy tắc khác nhau.

## 10. Xác minh tối thiểu khi tích hợp thư viện

Mục tiêu xác minh là chứng minh repository thật đã gọi đúng implementation từ JAR ngoài package quét.

Một kịch bản integration hữu ích gồm:

1. Khởi tạo application context bằng bộ dependency ứng dụng thực sự dùng.
2. Chỉ quét repository trong package ứng dụng.
3. Nạp thư viện chứa `ExternalSearch`, implementation và tài nguyên đăng ký.
4. Cung cấp một gateway giả có ghi nhận tham số được gọi.
5. Lấy `ProductRepository` từ context và gọi `searchExternal`.
6. Xác nhận gateway nhận đúng `Product.class`, chuỗi đã trim và giới hạn kết quả.
7. Thử một thao tác CRUD cơ bản để phát hiện việc cấu hình repository bị ảnh hưởng ngoài dự kiến.

Không chỉ kiểm thử bằng `new DefaultExternalSearch<>(gateway)`. Cách đó kiểm tra được logic implementation nhưng không kiểm tra tài nguyên JAR, cơ chế phát hiện hoặc composition của proxy.

Với thư viện hỗ trợ nhiều dòng Spring Data, chạy kịch bản tương ứng cho từng bộ phiên bản được công bố. Cần kiểm tra cả artifact đã đóng gói vì cấu hình test chạy trực tiếp từ source có thể che giấu lỗi mất tài nguyên khi tạo JAR.

Nếu ứng dụng dùng AOT hoặc native image, bổ sung xác minh trên cách đóng gói đó theo khả năng của phiên bản đang sử dụng. Không suy từ việc chạy JVM thông thường thành kết luận mọi hình thức phân phối đều đã hoạt động.

## 11. Chẩn đoán lỗi thường gặp

| Biểu hiện | Nguyên nhân cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Khởi tạo repository thất bại, framework cố phân tích phương thức fragment như truy vấn | Fragment implementation chưa được ghép; lỗi tạo query chỉ là một biểu hiện có thể gặp | Kiểm tra interface kế thừa, mapping, phiên bản hỗ trợ và phạm vi phát hiện |
| Interface fragment có trên classpath nhưng phương thức chưa hoạt động | JAR chứa API nhưng thiếu implementation hoặc tài nguyên đăng ký | Kiểm tra nội dung artifact thực tế |
| Mapping đúng nhưng phiên bản cũ không nhận | Hạ tầng repository chưa hỗ trợ đường đăng ký này | Dùng bridge phù hợp hoặc nâng bộ dependency sau khi kiểm chứng tương thích |
| Không tạo được implementation vì thiếu dependency | Không có bean `ExternalSearchGateway` | Cung cấp gateway trong application context |
| Có nhiều bean gateway | Constructor injection không có lựa chọn duy nhất | Làm rõ cấu hình chọn bean cho implementation |
| Chạy được trong IDE nhưng lỗi với JAR triển khai | Tài nguyên bị loại hoặc ghi đè khi đóng gói | Kiểm tra JAR cuối cùng và cách gộp `spring.factories` |
| Kết quả đi vào implementation không mong muốn | Đăng ký trùng contract hoặc nhiều đường phát hiện cùng tồn tại | Chọn một cấu hình ghép rõ ràng và xác minh bằng lời gọi thực tế |
| CRUD hoạt động nhưng phương thức fragment lỗi | Base repository đã được tạo, còn fragment có vấn đề riêng | Kiểm tra riêng composition và dependency của fragment |
| JPA hoạt động nhưng chuyển sang kho dữ liệu khác bị lỗi | Implementation có phụ thuộc đặc thù JPA | Tách adapter theo store hoặc giới hạn phạm vi hỗ trợ của thư viện |

Thêm `@ComponentScan` rộng cho toàn bộ `com.acme` có thể khiến một số bean xuất hiện, nhưng cũng có thể kéo theo những cấu hình không cần thiết. Khi điều tra lỗi, phải xác định đang thiếu bean phụ thuộc hay thiếu ánh xạ fragment, rồi sửa đúng điểm đó.

## 12. Bài thực hành

### Yêu cầu

Tách chức năng tìm kiếm ngoài thành thư viện `shared-search` và dùng trong hai repository `ProductRepository`, `CustomerRepository`.

Thư viện chứa:

- `ExternalSearch<T>`.
- `ExternalSearchGateway`.
- `DefaultExternalSearch<T>`.
- Tài nguyên đăng ký dành cho phiên bản có hỗ trợ.

Ứng dụng chứa:

- Hai domain type và hai repository tương ứng.
- Một gateway giả để quan sát lời gọi.
- Cấu hình repository chỉ hướng tới package ứng dụng.

### Trình tự

1. Xác định bộ phiên bản Spring Data thực tế và chọn đường đăng ký.
2. Nếu dùng mapping, cho hai repository kế thừa `ExternalSearch` với domain type tương ứng.
3. Gọi tìm kiếm qua từng repository và ghi nhận domain type gateway nhận được.
4. Thử chuỗi trắng và giới hạn bằng `0`; kiểm tra lỗi tham số xuất hiện trước khi gateway được gọi.
5. Trong một biến thể kiểm thử, bỏ tài nguyên đăng ký khỏi artifact và quan sát lỗi composition.
6. Với dòng phiên bản dùng bridge, tạo interface cùng implementation bridge trong package ứng dụng, giữ nguyên logic dùng chung.
7. Kiểm tra artifact cuối cùng còn đủ class và tài nguyên cần thiết.

### Tiêu chí hoàn thành

- Repository gọi được hành vi tìm kiếm qua proxy.
- Implementation dùng chung không cần nằm trong package repository của ứng dụng.
- Đường đăng ký phù hợp bộ phiên bản đã xác nhận.
- Các repository truyền đúng domain type và không dùng trạng thái chung để ghi nhớ repository hiện tại.
- Thư viện công bố rõ dependency, gateway cần cung cấp và phạm vi kho dữ liệu hỗ trợ.
- Các hành vi CRUD, truy vấn theo tên, projection hoặc auditing của repository không bị mặc định thay thế bởi fragment mới.

Fragment ngoài package quét là một cơ chế mở rộng có chủ đích: contract được chọn qua interface, implementation được tìm bằng đường đăng ký phù hợp, và các dependency được giải quyết trong Spring container. Một thư viện dùng chung chỉ hoàn chỉnh khi cả ba phần đó cùng được đóng gói và kiểm chứng trên bộ phiên bản mục tiêu.
