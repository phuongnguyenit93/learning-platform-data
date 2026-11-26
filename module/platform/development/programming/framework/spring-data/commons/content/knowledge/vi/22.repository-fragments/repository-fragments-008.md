# Triển khai thủ công và xử lý trường hợp tên bean mơ hồ

## 1. Bối cảnh: một fragment, nhiều cách tạo implementation

Trong chương **Repository fragment** của **SPRING_DATA_COMMONS**, fragment là một hợp đồng có implementation được ghép vào repository. Cơ chế này cho phép bổ sung hành vi mà các abstraction như `CrudRepository`, derived queries, phân trang hoặc projection chưa thể diễn đạt trực tiếp.

Bài học này tập trung vào hai việc:

- Tự khai báo bean implementation khi cần kiểm soát cách khởi tạo và dependency của fragment.
- Xác định implementation được sử dụng khi có nhiều lớp trùng tên hoặc nhiều bean liên quan đến cùng hợp đồng.

Ví dụ xuyên suốt là repository sản phẩm có thêm thao tác tìm kiếm văn bản. Phần ghép fragment thuộc cơ chế chung của Spring Data. Cách tìm kiếm thực tế, mapping entity/document, loại identifier và khả năng transaction phụ thuộc module lưu trữ đang dùng. Không thể suy ra một datastore hỗ trợ tìm kiếm toàn văn chỉ vì repository có một fragment tên `ProductSearch`.

Sau bài học, bạn cần phân biệt được ba câu hỏi: lớp nào được phát hiện làm implementation, bean nào cung cấp implementation đó, và dependency nào được truyền vào bean ấy.

## 2. Hợp đồng và quy ước tên cơ bản

### 2.1. Repository kế thừa interface fragment

Giả sử ứng dụng đã có domain `Product`, được mapping theo datastore của ứng dụng:

```java
package com.example.catalog.repository;

import org.springframework.data.repository.CrudRepository;

public interface ProductRepository
        extends CrudRepository<Product, Long>, ProductSearch {
}
```

Interface fragment chỉ mô tả hành vi bổ sung:

```java
package com.example.catalog.repository;

import java.util.List;

public interface ProductSearch {

    List<ProductSummary> findByText(String text, int limit);
}
```

Kết quả tìm kiếm là một DTO đơn giản:

```java
package com.example.catalog.repository;

public record ProductSummary(Long id, String name) {
}
```

`ProductSummary` trong ví dụ là kiểu trả về do code fragment tự xây dựng hoặc nhận từ adapter. Việc khai báo record này không tự kích hoạt cơ chế projection của derived queries.

### 2.2. Hậu tố mặc định là `Impl`

Với cấu hình mặc định, Spring Data tìm implementation có tên lớp hình thành từ tên interface fragment cộng hậu tố `Impl`:

| Thành phần | Tên trong ví dụ | Ý nghĩa |
|---|---|---|
| Repository ứng dụng | `ProductRepository` | Interface mà service sử dụng |
| Interface fragment | `ProductSearch` | Hợp đồng mở rộng |
| Lớp implementation theo quy ước | `ProductSearchImpl` | Ứng viên được cơ chế phát hiện implementation tìm kiếm |
| Tên bean mặc định theo quy ước | `productSearchImpl` | Tên dùng để đối chiếu, tham chiếu implementation |
| Bean repository | `productRepository` | Proxy repository được Spring Data tạo |

Tên bean theo ví dụ trên tuân theo cách viết lower camel case thông thường của Spring. Với tên lớp bắt đầu bằng nhiều chữ hoa, không nên tự đoán cách chuyển tên; hãy dùng tên bean khai báo tường minh để tránh nhầm lẫn.

Các ví dụ sử dụng lớp implementation trong cây package được cấu hình phát hiện cho repository. Đặt lớp đúng tên nhưng ngoài phạm vi phát hiện không bảo đảm lớp ấy được ghép vào repository.

Tên `productSearchImpl` gắn với **fragment `ProductSearch`**. Không đổi sang `productRepositoryImpl` chỉ vì repository cuối cùng là `ProductRepository`. Quy ước implementation gắn trực tiếp với tên repository là mô hình custom implementation cũ; không nên trộn nó vào thiết kế dựa trên các fragment độc lập.

### 2.3. Hai mối quan hệ cần giữ riêng

```text
ProductRepository
  extends CrudRepository<Product, Long>, ProductSearch
                                          |
                                          | ghép implementation
                                          v
                               bean productSearchImpl
                                          |
                                          | inject dependency
                                          v
                             bean catalogStoreSearch
```

Chọn `productSearchImpl` là bài toán ghép fragment. Chọn `catalogStoreSearch` để truyền vào constructor là bài toán dependency injection. Hai bài toán có thể cùng xuất hiện trong một lần khởi động ứng dụng nhưng được xử lý bằng các quy tắc khác nhau.

## 3. Một implementation có thể được wiring tự động

Ta đặt thao tác đặc thù datastore sau một hợp đồng do ứng dụng định nghĩa:

```java
package com.example.catalog.search;

import com.example.catalog.repository.ProductSummary;
import java.util.List;

public interface CatalogSearchOperations {

    List<ProductSummary> searchByText(String text, int limit);
}
```

`CatalogSearchOperations` không phải API có sẵn của Spring Data Commons. Ứng dụng phải cung cấp adapter thực sự, chẳng hạn bằng công cụ truy vấn của module lưu trữ hoặc bằng một search client. Adapter cần quy định rõ cách đối sánh văn bản, giới hạn kết quả và thứ tự trả về.

Một phiên bản implementation chỉ có một dependency có thể dùng constructor injection:

```java
package com.example.catalog.repository.fragment;

import com.example.catalog.repository.ProductSearch;
import com.example.catalog.repository.ProductSummary;
import com.example.catalog.search.CatalogSearchOperations;
import java.util.List;

public class ProductSearchImpl implements ProductSearch {

    private final CatalogSearchOperations operations;

    public ProductSearchImpl(CatalogSearchOperations operations) {
        this.operations = operations;
    }

    @Override
    public List<ProductSummary> findByText(String text, int limit) {
        if (text == null || text.isBlank()) {
            throw new IllegalArgumentException("text must not be blank");
        }
        if (limit < 1 || limit > 100) {
            throw new IllegalArgumentException("limit must be between 1 and 100");
        }
        return operations.searchByText(text.strip(), limit);
    }
}
```

Lớp nằm dưới `com.example.catalog.repository`, phù hợp với package repository đang xét. Khi được cơ chế repository implementation phát hiện và đăng ký, nó là bean được container quản lý và có thể nhận dependency qua constructor. Một constructor duy nhất không cần thêm `@Autowired`.

Không bắt buộc thêm `@Component` chỉ để Spring Data nhận diện một implementation đúng quy ước trong phạm vi phát hiện. Việc để container quét component và việc Spring Data tìm custom implementation có liên quan nhưng không phải cùng một thao tác.

Cấu hình tự động này thường đủ khi dependency đã là bean và việc lựa chọn dependency không mơ hồ. Khai báo bean thủ công hữu ích khi ứng dụng cần truyền thêm tham số, chọn một adapter cụ thể hoặc kiểm soát việc tạo object.

## 4. Wiring thủ công bằng một bean có tên đúng

### 4.1. Điều chỉnh implementation để nhận cấu hình

Giả sử giới hạn tìm kiếm cần được truyền khi tạo object. Trong biến thể này, thay lớp implementation ở phần trước bằng lớp sau; không giữ đồng thời hai định nghĩa cùng fully qualified class name:

```java
package com.example.catalog.repository.fragment;

import com.example.catalog.repository.ProductSearch;
import com.example.catalog.repository.ProductSummary;
import com.example.catalog.search.CatalogSearchOperations;
import java.util.List;
import java.util.Objects;

public class ProductSearchImpl implements ProductSearch {

    private final CatalogSearchOperations operations;
    private final int maxLimit;

    public ProductSearchImpl(
            CatalogSearchOperations operations,
            int maxLimit) {
        if (maxLimit < 1) {
            throw new IllegalArgumentException("maxLimit must be positive");
        }
        this.operations = Objects.requireNonNull(operations);
        this.maxLimit = maxLimit;
    }

    @Override
    public List<ProductSummary> findByText(String text, int limit) {
        if (text == null || text.isBlank()) {
            throw new IllegalArgumentException("text must not be blank");
        }
        if (limit < 1 || limit > maxLimit) {
            throw new IllegalArgumentException(
                    "limit must be between 1 and " + maxLimit);
        }
        return operations.searchByText(text.strip(), limit);
    }
}
```

`maxLimit` là tham số cấu hình của object. Không nên trông chờ container tự biết cần inject số nguyên nào nếu chưa khai báo cách cung cấp giá trị ấy.

### 4.2. Đăng ký bean `productSearchImpl`

```java
package com.example.catalog.config;

import com.example.catalog.repository.fragment.ProductSearchImpl;
import com.example.catalog.search.CatalogSearchOperations;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class CatalogFragmentConfiguration {

    @Bean(name = "productSearchImpl")
    public ProductSearchImpl productSearchImpl(
            @Qualifier("catalogStoreSearch")
            CatalogSearchOperations operations) {
        return new ProductSearchImpl(operations, 100);
    }
}
```

Trong cấu hình này:

1. Ứng dụng có một bean `CatalogSearchOperations` tên `catalogStoreSearch`, đã được adapter lưu trữ đăng ký.
2. Configuration được nạp vào application context.
3. Lớp `ProductSearchImpl` vẫn nằm trong phạm vi phát hiện implementation của repository.
4. Tên bean `productSearchImpl` khớp quy ước của fragment `ProductSearch`.
5. Hạ tầng Spring Data tham chiếu bean được khai báo sẵn theo tên đó thay vì tự tạo thêm implementation tương ứng.

Phần ví dụ chưa triển khai `catalogStoreSearch`, vì adapter này cần code và cấu hình của datastore thật. Khi áp dụng, phải cung cấp bean đó; chỉ sao chép configuration trên sẽ chưa tạo ra một ứng dụng có thể truy vấn dữ liệu.

Ở đây `@Qualifier("catalogStoreSearch")` lựa chọn dependency truyền vào factory method. Còn `@Bean(name = "productSearchImpl")` xác định tên implementation để ghép fragment. Hai annotation giải quyết hai việc riêng biệt.

Việc gọi `new ProductSearchImpl(...)` bên trong phương thức `@Bean` là cách tạo một bean hợp lệ: object trả về được container quản lý. Nếu service tự gọi `new` rồi sử dụng object ngoài container, object đó không tự trở thành fragment của repository.

### 4.3. Những điều wiring thủ công không tự làm

Khai báo `@Bean` không thay cho các điều kiện của repository composition:

- Repository vẫn cần kế thừa interface `ProductSearch`.
- Implementation phải thực hiện đúng hợp đồng đó.
- Cấu hình phát hiện repository và implementation phải phù hợp.
- Module lưu trữ và domain mapping phải được cấu hình đầy đủ.

Tên bean đúng là một phần của cấu hình, không phải một cơ chế đăng ký fragment bất kỳ bằng tên. Bài học này giữ lớp implementation đúng quy ước và trong phạm vi phát hiện; không dựa vào giả định rằng đặt một bean tùy ý tên `productSearchImpl` là đủ để hạ tầng tìm được fragment.

Các annotation bật repository thuộc module lưu trữ cụ thể. Ví dụ `@EnableJpaRepositories` thuộc Spring Data JPA, còn `@EnableMongoRepositories` thuộc Spring Data MongoDB. Không có một annotation `@EnableJpaRepositories` dùng chung cho mọi loại kho dữ liệu trong Commons.

### 4.4. Tên phương thức `@Bean` có ảnh hưởng

Nếu không khai báo `name`, tên bean mặc định là tên phương thức:

```java
@Bean
public ProductSearchImpl productSearchImpl(
        @Qualifier("catalogStoreSearch")
        CatalogSearchOperations operations) {
    return new ProductSearchImpl(operations, 100);
}
```

Bean vẫn tên `productSearchImpl`. Ngược lại, phương thức sau tạo bean tên `customSearch`:

```java
@Bean
public ProductSearchImpl customSearch(
        @Qualifier("catalogStoreSearch")
        CatalogSearchOperations operations) {
    return new ProductSearchImpl(operations, 100);
}
```

Bean `customSearch` không được dùng thay implementation theo quy ước chỉ vì nó cùng implement `ProductSearch`. Tùy cấu hình phát hiện, hạ tầng có thể đăng ký implementation khác dưới tên được mong đợi; việc tạo implementation khác cũng có thể thất bại vì constructor còn tham số chưa được cung cấp.

Nếu muốn tên phương thức khác, giữ tên bean tường minh:

```java
@Bean(name = "productSearchImpl")
public ProductSearchImpl createConfiguredSearchFragment(
        @Qualifier("catalogStoreSearch")
        CatalogSearchOperations operations) {
    return new ProductSearchImpl(operations, 100);
}
```

Các phương thức trên là những phương án thay thế nhau. Chỉ giữ một định nghĩa bean có tên `productSearchImpl` trong cấu hình đang chạy.

## 5. Mơ hồ khi nhiều package có cùng tên lớp implementation

### 5.1. Một tình huống dễ gặp

Một hệ thống thử nghiệm hai chiến lược tìm kiếm:

```text
com.example.catalog.repository.impl.local.ProductSearchImpl
com.example.catalog.repository.impl.remote.ProductSearchImpl
```

Cả hai lớp cùng implement `ProductSearch`, cùng có tên đơn giản `ProductSearchImpl` và cùng nằm trong phạm vi mà cơ chế phát hiện có thể tìm thấy.

Đây là hai lớp khác nhau đối với Java vì fully qualified class name khác nhau. Nhưng khác package chưa đủ để xác định lớp nào nên được ghép vào fragment. Không có hợp đồng rằng Spring Data sẽ ưu tiên package đứng trước theo bảng chữ cái, file được biên dịch trước hoặc implementation được viết trước.

Nếu cả hai cùng dẫn đến tên bean `productSearchImpl`, hệ thống không có một lựa chọn duy nhất. Tùy giai đoạn đăng ký và cách quét, ứng dụng có thể gặp lỗi phát hiện implementation mơ hồ hoặc xung đột tên bean từ component scanning.

### 5.2. Spring Data đối chiếu tên bean

Để minh họa quy tắc, xem hai khai báo rút gọn sau. Constructor và phương thức thực thi được lược bớt; đây là sơ đồ khai báo, không phải hai lớp Java hoàn chỉnh:

```java
// File trong package impl.local
package com.example.catalog.repository.impl.local;

public class ProductSearchImpl implements ProductSearch {
    // Constructor và findByText(...).
}
```

```java
// File trong package impl.remote
package com.example.catalog.repository.impl.remote;

import org.springframework.stereotype.Component;

@Component("remoteProductSearchImpl")
public class ProductSearchImpl implements ProductSearch {
    // Constructor và findByText(...).
}
```

Với quy ước mặc định, tên được mong đợi cho fragment `ProductSearch` là `productSearchImpl`:

| Ứng viên | Tên bean theo khai báo/quy ước | Khớp tên mong đợi? |
|---|---|---|
| Lớp trong `impl.local` | `productSearchImpl` | Có |
| Lớp trong `impl.remote` | `remoteProductSearchImpl` | Không |

Trong tình huống phát hiện hai ứng viên này, tên bean giúp xác định implementation local. Việc cả hai cùng implement `ProductSearch` không làm cho cả hai cùng được ghép để xử lý một phương thức.

Tên `remoteProductSearchImpl` có thêm chữ `remote` không tạo ra một ưu tiên đặc biệt. Nó chỉ là tên khác với tên quy ước đang được đối chiếu.

### 5.3. Chọn implementation remote bằng tên rõ ràng

Nếu muốn remote là implementation được ghép, một cách cấu hình là dành tên quy ước cho remote và đổi tên local:

```java
// Khai báo rút gọn trong package impl.local
@Component("localProductSearchImpl")
public class ProductSearchImpl implements ProductSearch {
    // Constructor và findByText(...).
}
```

```java
// Khai báo rút gọn trong package impl.remote
@Component("productSearchImpl")
public class ProductSearchImpl implements ProductSearch {
    // Constructor và findByText(...).
}
```

Khi ấy ứng viên remote có tên khớp `productSearchImpl`. Các lớp vẫn cần import `ProductSearch`, `Component` và cung cấp constructor/phương thức đầy đủ trong code thực tế.

Đây là phương án dùng tên component để phân biệt ứng viên. Nó là cấu hình thay thế cho ví dụ `@Bean` thủ công; không chồng thêm một `@Bean("productSearchImpl")` thứ hai vào cùng context.

Nếu một chiến lược không cần xuất hiện trong ứng dụng đang chạy, thu hẹp package phát hiện hoặc tách cấu hình theo profile thường dễ vận hành hơn việc giữ nhiều ứng viên rồi giải quyết bằng tên.

### 5.4. Tránh dựa vào bean overriding

Bật quyền ghi đè bean có thể làm định nghĩa đăng ký sau thay định nghĩa trước. Cách này không biểu đạt rõ lựa chọn nghiệp vụ và có thể che lỗi cấu hình.

Cần tạo một kết quả xác định: chỉ có một implementation hợp lệ cho phạm vi đó, hoặc chỉ có một ứng viên khớp tên được mong đợi. Nếu dùng profile, cần bảo đảm tập profile đang kích hoạt không làm hai định nghĩa tên `productSearchImpl` cùng tồn tại.

## 6. `@Primary` và `@Qualifier`: dùng đúng tầng

### 6.1. `@Primary` không thay hợp đồng chọn fragment

`@Primary` hỗ trợ lựa chọn bean khi container resolve dependency theo kiểu. Cơ chế dò implementation của fragment dựa vào quy ước phát hiện và đối chiếu tên bean; không nên dùng `@Primary` làm cách sửa cho hai lớp cùng khớp tên implementation.

Ví dụ đánh dấu một trong hai `ProductSearchImpl` là primary không giải thích được vì sao hạ tầng repository phải chọn đúng lớp đó trong quá trình dò fragment. Hãy sửa tên bean hoặc phạm vi ứng viên.

### 6.2. `@Qualifier` trên factory method chọn dependency

Giả sử context có hai adapter:

```text
catalogStoreSearch  -> CatalogSearchOperations
catalogIndexSearch  -> CatalogSearchOperations
```

Tham số dưới đây có thể mơ hồ vì cả hai bean cùng thỏa kiểu:

```java
@Bean(name = "productSearchImpl")
public ProductSearchImpl productSearchImpl(
        CatalogSearchOperations operations) {
    return new ProductSearchImpl(operations, 100);
}
```

Đặt qualifier lên tham số giải quyết đúng điểm cần lựa chọn:

```java
@Bean(name = "productSearchImpl")
public ProductSearchImpl productSearchImpl(
        @Qualifier("catalogIndexSearch")
        CatalogSearchOperations operations) {
    return new ProductSearchImpl(operations, 100);
}
```

Tên fragment vẫn là `productSearchImpl`; chỉ adapter bên trong đổi thành `catalogIndexSearch`. Nếu một adapter là mặc định toàn ứng dụng, `@Primary` có thể phù hợp ở tầng dependency này, nhưng cần đánh giá ảnh hưởng đến những điểm injection khác.

Đặt `@Qualifier` ở service nhận `ProductRepository` không thay đổi cách fragment bên trong repository đã được ghép lúc khởi tạo. Service lựa chọn bean repository; nó không cấu hình lại composition của bean ấy.

### 6.3. Bảng chẩn đoán nhanh

| Dấu hiệu | Câu hỏi cần kiểm tra | Hướng xử lý |
|---|---|---|
| Có hai lớp `ProductSearchImpl` trong hai package | Có bao nhiêu ứng viên trong phạm vi phát hiện? | Thu hẹp phạm vi hoặc làm tên bean phân biệt rõ |
| Có hai định nghĩa cùng tên `productSearchImpl` | Tên này được khai báo qua component, `@Bean` hay cả hai? | Giữ một định nghĩa có chủ đích |
| Không chọn được `CatalogSearchOperations` | Constructor/factory method có nhiều bean cùng kiểu? | Dùng qualifier hoặc primary phù hợp cho dependency |
| Có bean `customSearch` nhưng repository không dùng | Tên bean có khớp quy ước của fragment không? | Khai báo `productSearchImpl` và giữ điều kiện phát hiện hợp lệ |
| Framework cố suy diễn `findByText` thành query | Fragment có được nhận diện và ghép không? | Kiểm tra interface kế thừa, tên lớp, hậu tố và package trước |
| Repository không xuất hiện trong context | Đã bật đúng hạ tầng repository của datastore chưa? | Kiểm tra cấu hình module lưu trữ và phạm vi repository |

Không kết luận từ tên exception đơn lẻ. Một lỗi tạo repository có thể bọc lỗi tạo fragment, rồi bên trong tiếp tục bọc lỗi tạo adapter. Hãy lần theo nguyên nhân tới bean hoặc constructor cụ thể bị lỗi.

## 7. Khi đổi hậu tố implementation

Hậu tố mặc định `Impl` có thể được thay qua cấu hình repository của module cụ thể. Ví dụ riêng cho một ứng dụng dùng Spring Data JPA:

```java
package com.example.catalog.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;

@Configuration
@EnableJpaRepositories(
        basePackages = "com.example.catalog.repository",
        repositoryImplementationPostfix = "Custom")
public class CatalogJpaRepositoryConfiguration {
}
```

Sau thay đổi này, các tên tương ứng cho fragment trong phạm vi cấu hình là:

| Thành phần | Mặc định | Khi hậu tố là `Custom` |
|---|---|---|
| Interface fragment | `ProductSearch` | `ProductSearch` |
| Lớp theo quy ước | `ProductSearchImpl` | `ProductSearchCustom` |
| Tên bean theo quy ước | `productSearchImpl` | `productSearchCustom` |

`ProductSearchCustom` phải thực sự implement `ProductSearch`. Nếu wiring thủ công, đổi tên bean tương ứng và trả về implementation mới. Chỉ đổi annotation cấu hình nhưng giữ nguyên các tên cũ sẽ làm quy ước không còn đồng bộ.

Ví dụ `@EnableJpaRepositories` yêu cầu module JPA; không sao chép nó sang ứng dụng MongoDB hoặc một module khác chỉ để dùng thuộc tính hậu tố. Hãy áp dụng cấu hình tương đương mà module đang dùng cung cấp.

Việc đổi hậu tố có thể ảnh hưởng các fragment khác trong cùng phạm vi cấu hình. Với nhu cầu chỉ chọn một dependency khác, điều chỉnh factory method thường hẹp và rõ hơn thay đổi quy ước cho cả nhóm repository.

## 8. Giới hạn chức năng và vòng đời của implementation

### 8.1. Fragment không tự được thêm mọi hành vi của base repository

Ghép `ProductSearch` vào `ProductRepository` không biến `findByText` thành một derived query, cũng không tự cung cấp phân trang, auditing hoặc transaction cho thuật toán tìm kiếm.

- Nếu thêm `Pageable`, implementation cần áp dụng giới hạn, offset và sort đúng khả năng backend; nếu trả `Page`, cần xác định cách tính tổng phù hợp.
- Nếu cần projection, phải xác định fragment tạo hoặc ánh xạ kết quả như thế nào.
- Nếu fragment ghi dữ liệu bằng một client riêng, cần xem đường ghi đó có đi qua cơ chế auditing của module hay không.
- Nếu cần transaction, phải cấu hình transaction manager, ranh giới giao dịch và cơ chế proxy phù hợp với module lưu trữ. Không suy ra custom method tự kế thừa mọi thiết lập transaction của phương thức CRUD có sẵn.

Đối với ví dụ này, thao tác chỉ nhận `limit`; nó chưa phải API phân trang và không trả tổng số bản ghi.

### 8.2. Bean thường được dùng chung giữa nhiều lời gọi

Với scope mặc định, implementation là singleton. Một fragment interface có thể được nhiều repository sử dụng, nên implementation không nên giữ trạng thái tạm của request trong field:

```java
// Không dùng field này để lưu tham số của lần gọi hiện tại.
private String currentText;
```

Hãy giữ tham số tìm kiếm trong biến cục bộ và bảo đảm dependency có cách sử dụng phù hợp khi nhiều luồng gọi đồng thời. Hai field `operations` và `maxLimit` trong ví dụ là dependency/cấu hình ổn định; chúng không lưu tiến trình của từng request.

### 8.3. Tên bean không đồng nghĩa với vai trò nghiệp vụ

Tên `productSearchImpl` là chi tiết cấu hình composition. Service thông thường nên nhận `ProductRepository` và gọi qua hợp đồng repository, thay vì phụ thuộc trực tiếp vào tên bean implementation.

Tra cứu implementation bằng tên hữu ích khi kiểm tra cấu hình hoặc viết kiểm thử tích hợp. Nếu service liên tục phải chọn giữa các implementation fragment theo tên, hãy xem lại thiết kế: nhu cầu chọn chiến lược theo từng request thường phù hợp với một abstraction điều phối riêng hơn là thay composition của một singleton repository.

## 9. Quy trình kiểm tra khi ứng dụng chọn sai implementation

### Bước 1: ghi rõ tên đang được mong đợi

Đối với ví dụ mặc định:

```text
fragment interface : ProductSearch
implementation     : ProductSearchImpl
bean name          : productSearchImpl
```

Đọc cấu hình repository đang có hiệu lực để xác định hậu tố, thay vì suy đoán từ tên lớp trong source.

### Bước 2: kiểm tra hợp đồng và phạm vi phát hiện

Xác nhận `ProductRepository` kế thừa `ProductSearch`, implementation implements đúng interface và nằm trong phạm vi phù hợp. Nếu có nhiều cấu hình repository, xác định cấu hình nào quản lý repository này.

Trong ứng dụng có nhiều module Spring Data, giới hạn package repository rõ ràng còn giúp tránh nhầm module lưu trữ chịu trách nhiệm tạo proxy.

### Bước 3: liệt kê tên khai báo cho từng ứng viên

Với mỗi lớp phù hợp, xem tên từ `@Component`, tên từ `@Bean`, alias nếu có và configuration/profile tạo bean. Đặc biệt tìm trường hợp một lớp vừa được component scanning đăng ký vừa được factory method tạo thêm instance.

Không giải quyết bằng cách thêm tiếp một bean tên giống nhau. Trước hết phải xác định định nghĩa hiện có nào là định nghĩa mong muốn.

### Bước 4: kiểm tra dependency của bean đã chọn

Khi tên fragment đã đúng, xem constructor/factory method còn dependency nào mơ hồ hoặc thiếu. `CatalogSearchOperations` có hai bean là lỗi khác với hai ứng viên `ProductSearchImpl`.

Nếu điều chỉnh qualifier, phải đặt ở điểm nhận dependency đang mơ hồ, chẳng hạn tham số `operations` của phương thức `@Bean`.

### Bước 5: xác nhận cả cấu hình lẫn hành vi

Trong kiểm thử tích hợp có context, có thể kiểm tra bean mong đợi tồn tại:

```java
ProductSearch fragment = context.getBean(
        "productSearchImpl", ProductSearch.class);
```

Đoạn trên chỉ xác nhận một bean có đúng tên và hợp đồng. Nó chưa chứng minh repository proxy đang gọi bean ấy.

Cần gọi tiếp qua repository:

```java
ProductRepository repository = context.getBean(ProductRepository.class);

var result = repository.findByText("spring", 5);
```

Trong kiểm thử, dùng adapter giả hoặc spy để ghi nhận lời gọi và trả một kết quả xác định. Xác nhận lời gọi qua repository tới đúng adapter, nhận đúng `"spring"` và giới hạn `5`, đồng thời kết quả trả về đúng mong đợi. Nếu có hai chiến lược local/remote, mỗi adapter nên có dấu hiệu kiểm thử riêng để phân biệt.

Khi tra bean theo kiểu `ProductSearch`, lưu ý repository proxy cũng có thể thỏa kiểu ấy vì `ProductRepository` kế thừa fragment. Danh sách bean theo kiểu không mặc nhiên chỉ chứa implementation thuần; hãy kiểm tra theo tên và kiểm tra hành vi qua repository.

Những kiểm tra quan trọng cho thay đổi wiring gồm: context khởi tạo được, implementation có tên đúng, dependency là adapter dự kiến và phương thức trên repository thực sự đi qua fragment.

## 10. Bài thực hành có hướng dẫn

### Bài 1: chuyển từ tự tạo sang wiring thủ công

Bắt đầu với một repository hoạt động cùng `ProductSearchImpl` chỉ có constructor nhận `CatalogSearchOperations`.

1. Thêm tham số `maxLimit` như phần 4.
2. Khai báo đúng một bean `productSearchImpl`, truyền `maxLimit = 20` và adapter có tên cụ thể.
3. Gọi `findByText("spring", 5)` qua `ProductRepository`; xác nhận adapter nhận giới hạn `5`.
4. Gọi với giới hạn `21`; xác nhận nhận lỗi đầu vào và adapter không thực hiện tìm kiếm.

Mục tiêu là chứng minh bean tự cấu hình được ghép vào repository và tham số constructor thực sự tác động tới hành vi.

### Bài 2: tạo rồi xử lý ứng viên mơ hồ

Dùng hai implementation cùng tên đơn giản `ProductSearchImpl` trong hai package đều thuộc phạm vi phát hiện. Triển khai đầy đủ cùng hợp đồng, nhưng cho adapter giả trả dữ liệu phân biệt được.

1. Quan sát hành vi khởi tạo khi không có lựa chọn duy nhất; ghi lại ứng viên hoặc tên bean trong nguyên nhân lỗi.
2. Đặt tên bean local là `localProductSearchImpl` và remote là `productSearchImpl`.
3. Gọi qua repository và xác nhận kết quả từ remote.
4. Đổi tên để local sở hữu `productSearchImpl`; xác nhận hành vi chuyển sang local.

Không dùng bean overriding để làm bài chạy được. Kết quả cần thể hiện quan hệ giữa tên mong đợi và implementation được chọn.

### Bài 3: phân biệt mơ hồ fragment với mơ hồ dependency

Giữ duy nhất một lớp `ProductSearchImpl`, rồi tạo hai bean `CatalogSearchOperations`. Để tham số factory method chưa có qualifier và quan sát lỗi lựa chọn dependency. Sau đó thêm `@Qualifier` cho đúng adapter.

Kết luận cần rút ra: số lượng implementation fragment đã là một vẫn không bảo đảm mọi dependency của nó đều được resolve duy nhất.

## 11. Các điểm cần nhớ

- Thiết kế fragment bắt đầu từ interface mở rộng, lớp implementation và repository kế thừa interface ấy.
- Quy ước mặc định trong ví dụ là `ProductSearch` → `ProductSearchImpl` → `productSearchImpl`.
- Wiring thủ công khai báo bean dưới tên hạ tầng mong đợi, đồng thời giữ điều kiện phát hiện và composition hợp lệ.
- Khi nhiều implementation phù hợp xuất hiện, tên bean giúp phân biệt; khác package hoặc thêm `@Primary` không thay cho cấu hình lựa chọn fragment rõ ràng.
- Qualifier trên constructor hoặc factory method lựa chọn dependency của implementation.
- Đổi hậu tố implementation phải đồng bộ tên lớp, tên bean và cấu hình của module lưu trữ.
- Kiểm tra cuối cùng phải đi qua repository proxy để chứng minh đúng implementation và đúng adapter đang được sử dụng.