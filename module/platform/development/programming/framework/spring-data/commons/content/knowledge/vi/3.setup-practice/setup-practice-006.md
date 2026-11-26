# Thiết kế ví dụ độc lập với chi tiết cấu hình cơ sở dữ liệu

Một bài thực hành Spring Data Commons nên giúp người học nhận ra abstraction đang sử dụng trước khi phải giải quyết URL kết nối, tài khoản cơ sở dữ liệu, migration hoặc cấu hình driver. Nếu mọi ví dụ đều bắt đầu bằng việc khởi động toàn bộ ứng dụng, lỗi cấu hình môi trường có thể che mất điều cần học về repository, phân trang, sắp xếp hoặc hình dạng kết quả.

Cách tiếp cận trong bài này là xây dựng một ví dụ tra cứu khách hàng có dữ liệu cố định, ranh giới truy cập dữ liệu rõ ràng và có thể kiểm tra bằng Java thuần cùng các kiểu của Commons. Sau đó, một adapter dùng store thật có thể được bổ sung phía sau ranh giới đó.

Ví dụ vẫn chủ động phụ thuộc Spring Data Commons để sử dụng `Page`, `PageImpl`, `PageRequest`, `Pageable` và `Sort`. Tính độc lập ở đây là độc lập với **chi tiết cấu hình và triển khai của một cơ sở dữ liệu cụ thể**, không phải loại bỏ mọi dependency Spring Data.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Chọn một lát cắt nghiệp vụ nhỏ, có đầu vào và kết quả kiểm chứng được.
- Tách mô hình của ví dụ khỏi entity hoặc document mapping của store.
- Dùng constructor injection để thay nguồn dữ liệu mà không đổi logic ứng dụng.
- Tạo fixture có thứ tự và số lượng kết quả ổn định để học phân trang, sắp xếp.
- Phân biệt điều được kiểm tra bằng dữ liệu trong bộ nhớ với điều phải kiểm tra trên store thật.
- Mở rộng ví dụ sang CRUD, derived queries, projection, Query by Example hoặc auditing mà không trộn mọi cấu hình vào cùng một lớp.

## 2. Chọn một yêu cầu đủ nhỏ và rõ ràng

Ví dụ phục vụ yêu cầu:

> Liệt kê khách hàng đang hoạt động theo từng trang, sắp xếp tên tăng dần và dùng ID tăng dần để phân định những khách hàng có cùng tên. Mỗi kết quả chỉ cần ID và tên.

Quy ước của bài thực hành:

| Thành phần | Quy ước |
| --- | --- |
| Chỉ số trang | Bắt đầu từ `0` |
| Kích thước trang | Từ `1` đến `50` |
| Điều kiện | Chỉ lấy khách hàng có `active = true` |
| Thứ tự | `name ASC`, sau đó `id ASC` |
| Kết quả | `Page<CustomerCard>` |
| Trang vượt quá dữ liệu | Nội dung rỗng, vẫn giữ thông tin tổng phù hợp |
| Đầu vào không hợp lệ | Báo lỗi trước khi gọi nguồn dữ liệu |

Bài tập cố định thứ tự thay vì nhận mọi tên trường sắp xếp từ bên ngoài. Lựa chọn này giảm số yếu tố cần xử lý trong lần thực hành đầu tiên. Sau khi nắm được luồng chính, có thể bổ sung một hợp đồng sắp xếp có danh sách trường được phép.

Các fixture dùng tên đơn giản như `An`, `Binh`, `Dung` và ID có độ dài thống nhất. Điều đó giúp dễ dự đoán thứ tự khi đọc bài. Khi mở rộng sang tiếng Việt có dấu, chữ hoa/chữ thường hoặc giá trị `null`, cần định nghĩa thêm quy tắc so sánh và đối chiếu với collation của store.

## 3. Tách ví dụ thành bốn thành phần

```text
Kiểm thử hoặc nơi gọi
        |
        v
CustomerCatalog
  - kiểm tra đầu vào
  - tạo Pageable
  - chuyển kết quả sang CustomerCard
        |
        v
CustomerReader
  - hợp đồng đọc khách hàng đang hoạt động
        |
        +-- InMemoryCustomerReader cho bài tập độc lập
        |
        +-- Adapter dùng store thật khi tích hợp
```

Vai trò của từng phần:

| Thành phần | Chịu trách nhiệm | Không cần biết |
| --- | --- | --- |
| `Customer` | Dữ liệu khách hàng dùng trong ví dụ | Bảng, collection, datasource, repository factory |
| `CustomerReader` | Hợp đồng đọc đã được ứng dụng chọn | URL, mật khẩu, driver và cách biểu diễn truy vấn |
| `CustomerCatalog` | Quy tắc trang và hình dạng dữ liệu trả về | Entity mapping hoặc API truy cập store |
| `InMemoryCustomerReader` | Cung cấp dữ liệu cố định theo phạm vi bài tập | Cấu hình cơ sở dữ liệu và giao dịch |

`CustomerReader` là interface do ứng dụng định nghĩa, không phải repository được Spring Data tự triển khai. Nó giúp thay nguồn dữ liệu cho bài tập bằng một hợp đồng nhỏ.

Khi thêm store thật, adapter có thể sử dụng một repository do Spring Data tạo ở bên trong. Hai interface có vai trò khác nhau: một cái mô tả nhu cầu của ứng dụng, cái còn lại là điểm tích hợp với công nghệ lưu trữ.

## 4. Dependency tối thiểu và cách tổ chức mã

Phần thực hành độc lập cần:

- Java hỗ trợ cú pháp `record` và các API Java được sử dụng trong ví dụ.
- `spring-data-commons` theo bộ phiên bản tương thích của dự án.
- JUnit Jupiter nếu thực hiện các kiểm thử minh họa.

Không cần tạo application context để khởi tạo những đối tượng dưới đây. Không cần datasource vì không có đường thực thi nào gọi một store.

Nếu dependency management đã cung cấp phiên bản, phần dependency Maven có thể có dạng:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.data</groupId>
        <artifactId>spring-data-commons</artifactId>
    </dependency>
    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Đây là một phần cấu hình, không phải toàn bộ build. Compiler, công cụ chạy test và phiên bản thư viện phải được cấu hình phù hợp với dự án. Trong một ứng dụng đã dùng starter dữ liệu, Commons có thể đã xuất hiện qua dependency bắc cầu; cần dùng chung nguồn quản lý phiên bản.

Trong các đoạn Java tiếp theo, mỗi kiểu public nằm trong file riêng theo tên kiểu và cùng package minh họa. Kiểm thử cũng đặt trong package đó. Các tên file trong bài là gợi ý tổ chức mã khi người học tự thực hành.

## 5. Định nghĩa dữ liệu không gắn mapping của store

### 5.1. Mô hình khách hàng

```java
import java.util.Objects;

public record Customer(String id, String name, boolean active) {
    public Customer {
        Objects.requireNonNull(id, "id");
        Objects.requireNonNull(name, "name");
    }
}
```

ID được fixture cung cấp trực tiếp. Ví dụ không đặt ra giả định rằng mọi store đều sinh ID theo một cơ chế giống nhau.

Mô hình cũng chưa có annotation JPA hay MongoDB. Đây là kiểu dữ liệu cho nhu cầu của bài tập, không phải lời hứa rằng record này có thể được sử dụng nguyên trạng làm entity trên mọi công nghệ persistence.

Khi tích hợp, có thể tạo entity hoặc document riêng và chuyển đổi sang `Customer`. Cách tách này giúp đặc điểm như constructor cho provider, tên cột, tên collection hoặc metadata version không lan vào phần học phân trang.

### 5.2. Kiểu kết quả phục vụ nơi gọi

```java
public record CustomerCard(String id, String name) {
}
```

`CustomerCard` chỉ chứa dữ liệu mà thao tác liệt kê cần trả về. Việc tạo kiểu này giúp hợp đồng đầu ra rõ ràng.

Tuy nhiên, chuyển `Customer` thành `CustomerCard` trong bộ nhớ chưa chứng minh truy vấn store chỉ đọc hai trường. Đây là phép chuyển đổi kết quả ở tầng ứng dụng. Projection tại repository là một cơ chế khác, cần module hỗ trợ và phải được kiểm tra khi tích hợp.

## 6. Định nghĩa hợp đồng đọc nhỏ

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

public interface CustomerReader {
    Page<Customer> findActive(Pageable pageable);
}
```

Hợp đồng trong phạm vi bài tập là:

- Chỉ trả khách hàng đang hoạt động.
- Nhận yêu cầu phân trang có kích thước hợp lệ.
- Hỗ trợ thứ tự `name ASC`, `id ASC` mà bài tập đã chọn.
- Trả nội dung trang cùng tổng số khách hàng khớp điều kiện.
- Không có kết quả thì trả trang có nội dung rỗng.

Interface dùng `Pageable` và `Page` để thực hành Commons trực tiếp. Nếu một ứng dụng có yêu cầu độc lập với cả thư viện phân trang, nó có thể định nghĩa kiểu yêu cầu và kết quả riêng. Trong bài này, phụ thuộc Commons là lựa chọn có chủ đích.

Không cho `CustomerReader` kế thừa toàn bộ `CrudRepository` khi chỉ cần một thao tác đọc. Làm như vậy sẽ buộc implementation thực hành phải cung cấp nhiều phương thức không liên quan, đồng thời dễ tạo cảm giác rằng nó đã mô phỏng đầy đủ semantics của repository thật.

## 7. Viết logic ứng dụng bằng constructor injection

```java
import java.util.Objects;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;

public final class CustomerCatalog {
    private final CustomerReader reader;

    public CustomerCatalog(CustomerReader reader) {
        this.reader = Objects.requireNonNull(reader, "reader");
    }

    public Page<CustomerCard> listActive(int page, int size) {
        if (page < 0) {
            throw new IllegalArgumentException("page must be >= 0");
        }
        if (size < 1 || size > 50) {
            throw new IllegalArgumentException("size must be between 1 and 50");
        }

        Sort order = Sort.by(
                Sort.Order.asc("name"),
                Sort.Order.asc("id"));

        Pageable pageable = PageRequest.of(page, size, order);

        return reader.findActive(pageable)
                .map(customer -> new CustomerCard(
                        customer.id(), customer.name()));
    }
}
```

Ở đây có ba điều đáng quan sát:

1. Kiểm tra đầu vào diễn ra trước khi đọc dữ liệu.
2. `PageRequest` mang số trang, kích thước và thứ tự mà ứng dụng đã chọn.
3. `Page.map` chuyển nội dung sang kiểu khác, đồng thời giữ ngữ cảnh phân trang của kết quả.

Constructor nhận `CustomerReader` nên kiểm thử có thể cung cấp implementation trong bộ nhớ. Khi tích hợp store, nơi lắp ghép chỉ cần cung cấp adapter khác.

Lớp không cần annotation `@Service` để có thể hoạt động. Trong ứng dụng Spring, có thể đăng ký nó thành bean bằng cơ chế cấu hình phù hợp. Khả năng kiểm tra logic không phụ thuộc việc dùng container để tạo đối tượng.

## 8. Tạo implementation trong bộ nhớ đúng phạm vi bài tập

```java
import java.util.Comparator;
import java.util.List;
import java.util.Objects;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;

public final class InMemoryCustomerReader implements CustomerReader {
    private static final Sort SUPPORTED_ORDER = Sort.by(
            Sort.Order.asc("name"),
            Sort.Order.asc("id"));

    private final List<Customer> customers;

    public InMemoryCustomerReader(List<Customer> customers) {
        this.customers = List.copyOf(customers);
    }

    @Override
    public Page<Customer> findActive(Pageable pageable) {
        Objects.requireNonNull(pageable, "pageable");
        if (pageable.isUnpaged()) {
            throw new IllegalArgumentException("paged request required");
        }
        if (!SUPPORTED_ORDER.equals(pageable.getSort())) {
            throw new IllegalArgumentException("unsupported sort");
        }

        List<Customer> matches = customers.stream()
                .filter(Customer::active)
                .sorted(Comparator.comparing(Customer::name)
                        .thenComparing(Customer::id))
                .toList();

        long offset = pageable.getOffset();
        int from = (int) Math.min(offset, (long) matches.size());
        int to = (int) Math.min(
                (long) from + pageable.getPageSize(),
                (long) matches.size());

        List<Customer> content = List.copyOf(matches.subList(from, to));
        return new PageImpl<>(content, pageable, matches.size());
    }
}
```

### 8.1. Vì sao phải lọc rồi mới phân trang?

Nội dung và tổng số đều phải xuất phát từ tập khách hàng đang hoạt động. Nếu cắt trang trước rồi mới lọc, một trang có thể ít phần tử một cách sai lệch và tổng số không còn thể hiện đúng truy vấn.

Thứ tự đúng của implementation minh họa là:

```text
Dữ liệu nguồn
    -> lọc active
    -> sắp xếp name, id
    -> tính vị trí trang
    -> lấy nội dung trang
    -> tạo Page với tổng số khớp điều kiện
```

### 8.2. Vì sao không dùng thứ tự của danh sách nguồn?

Nếu fixture đã vô tình nằm đúng thứ tự, một implementation quên sắp xếp vẫn có thể cho kết quả đúng trong kiểm thử đơn giản. Bài tập sẽ dùng fixture khác thứ tự mong muốn, đồng thời có hai khách hàng cùng tên để kiểm tra khóa phụ ID.

Khóa phụ giúp thứ tự xác định hơn khi giá trị tên trùng nhau. Nó không tạo ảnh chụp dữ liệu xuyên suốt nhiều lần đọc trên hệ thống có cập nhật đồng thời.

### 8.3. Vì sao implementation từ chối cách sắp xếp khác?

Implementation chỉ thực hiện đúng một tập hành vi nhỏ. Nếu nhận một `Sort` bất kỳ rồi bỏ qua nó, kiểm thử có thể thành công dù ứng dụng yêu cầu thứ tự mà nguồn dữ liệu không thực hiện.

Từ chối yêu cầu ngoài phạm vi giúp giới hạn được nhìn thấy. Khi cần thêm thứ tự khác, hãy bổ sung nó vào hợp đồng và implementation một cách rõ ràng.

### 8.4. Cách xử lý trang vượt quá dữ liệu

`Pageable.getOffset()` có kiểu `long`. Ví dụ giới hạn offset bằng kích thước danh sách trước khi ép sang `int`, phù hợp với chỉ số của `List`.

Nếu offset vượt quá số kết quả, `from` và `to` cùng bằng kích thước tập khớp. Nội dung trang rỗng, trong khi tổng số vẫn lấy từ `matches.size()`.

Không dùng số phần tử của riêng trang làm `total`. Với trang có hai phần tử trong tổng bốn kết quả, `total = 2` sẽ làm sai thông tin điều hướng.

## 9. Tạo fixture có kết quả kiểm chứng được

Sử dụng dữ liệu sau:

| ID | Tên | Đang hoạt động |
| --- | --- | --- |
| `c-001` | `Binh` | Có |
| `c-002` | `An` | Có |
| `c-003` | `Chi` | Không |
| `c-004` | `An` | Có |
| `c-005` | `Dung` | Có |

Sau khi lọc và sắp xếp, thứ tự mong muốn là:

```text
c-002 An
c-004 An
c-001 Binh
c-005 Dung
```

Với kích thước trang `2`:

| Trang | Nội dung | Tổng phần tử | Tổng trang | Còn trang tiếp theo |
| --- | --- | --- | --- | --- |
| `0` | `c-002`, `c-004` | `4` | `2` | Có |
| `1` | `c-001`, `c-005` | `4` | `2` | Không |
| `2` | Rỗng | `4` | `2` | Không |

Fixture này đồng thời làm lộ các lỗi phổ biến: quên lọc trạng thái, quên sắp xếp, quên khóa phụ và dùng kích thước trang thay cho tổng số.

Không tạo ID ngẫu nhiên hoặc đọc thời gian hệ thống cho một ví dụ không cần các yếu tố đó. Dữ liệu cố định giúp người học suy luận được kết quả trước khi chạy.

## 10. Kiểm tra mà không khởi động Spring hoặc cơ sở dữ liệu

Các kiểm thử sau dùng JUnit Jupiter và khởi tạo đối tượng trực tiếp:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.data.domain.Page;

class CustomerCatalogTest {
    private CustomerCatalog catalog() {
        List<Customer> fixture = List.of(
                new Customer("c-001", "Binh", true),
                new Customer("c-002", "An", true),
                new Customer("c-003", "Chi", false),
                new Customer("c-004", "An", true),
                new Customer("c-005", "Dung", true));

        return new CustomerCatalog(new InMemoryCustomerReader(fixture));
    }

    @Test
    void listsActiveCustomersInStablePages() {
        CustomerCatalog catalog = catalog();

        Page<CustomerCard> first = catalog.listActive(0, 2);
        Page<CustomerCard> second = catalog.listActive(1, 2);

        assertEquals(List.of(
                new CustomerCard("c-002", "An"),
                new CustomerCard("c-004", "An")), first.getContent());
        assertEquals(4L, first.getTotalElements());
        assertEquals(2, first.getTotalPages());
        assertTrue(first.hasNext());

        assertEquals(List.of(
                new CustomerCard("c-001", "Binh"),
                new CustomerCard("c-005", "Dung")), second.getContent());
        assertEquals(4L, second.getTotalElements());
        assertFalse(second.hasNext());
    }

    @Test
    void returnsEmptyContentBeyondTheLastPage() {
        Page<CustomerCard> result = catalog().listActive(2, 2);

        assertTrue(result.getContent().isEmpty());
        assertEquals(4L, result.getTotalElements());
        assertEquals(2, result.getTotalPages());
        assertFalse(result.hasNext());
    }

    @Test
    void rejectsInvalidInputBeforeReadingData() {
        CustomerReader unexpectedRead = pageable -> {
            throw new AssertionError("reader must not be called");
        };
        CustomerCatalog catalog = new CustomerCatalog(unexpectedRead);

        assertThrows(IllegalArgumentException.class,
                () -> catalog.listActive(-1, 2));
        assertThrows(IllegalArgumentException.class,
                () -> catalog.listActive(0, 0));
        assertThrows(IllegalArgumentException.class,
                () -> catalog.listActive(0, 51));
    }
}
```

Những kiểm thử này xác nhận kết quả mà người gọi quan sát được: lọc, thứ tự, phân trang, hình dạng đầu ra và xử lý đầu vào sai. Chúng không cần xác nhận từng lời gọi nội bộ hoặc chi tiết constructor.

Kiểm thử cuối cố ý làm nguồn đọc thất bại nếu được gọi. Nhờ đó, nó kiểm tra được quy tắc đầu vào sai phải bị từ chối trước khi truy cập dữ liệu, thay vì chỉ kiểm tra rằng một exception nào đó xuất hiện.

Không có `@SpringBootTest` hay annotation kích hoạt repository vì đối tượng được tạo trực tiếp. Nếu chạy toàn bộ application context trong một bài thực hành khác, các auto-configuration của ứng dụng vẫn có thể yêu cầu datasource. Đó là phạm vi khởi tạo khác với bài tập hiện tại.

## 11. Những điều implementation trong bộ nhớ không chứng minh

Implementation trên là một nguồn dữ liệu giả có hành vi giới hạn. Nó không phải một Spring Data store module và cũng không phải bộ mô phỏng đầy đủ cơ sở dữ liệu.

| Điều cần học hoặc kiểm tra | Bài tập độc lập làm được gì? | Cần xác nhận thêm ở store thật |
| --- | --- | --- |
| Phân trang | Thể hiện số trang, kích thước, tổng số và nội dung mong muốn | Truy vấn phân trang, chiến lược đếm, chi phí offset |
| Sắp xếp | Tạo thứ tự xác định cho fixture | Collation, `null`, chỉ mục và mapping tên thuộc tính |
| Derived queries | Mô tả nhu cầu tìm khách hàng active | Parser, metadata, toán tử và truy vấn do module tạo |
| Projection | Chuyển mô hình sang `CustomerCard` | Projection tại repository và tối ưu dữ liệu đọc |
| Query by Example | Có thể kiểm tra cách ứng dụng tạo probe và matcher | Module hỗ trợ và cách store thực thi phép so khớp |
| Auditing | Có thể kiểm tra quy tắc ứng dụng nếu truyền nguồn thời gian/chủ thể vào | Cấu hình, callback, metadata và đường ghi của module |
| Giao dịch, khóa | Chưa thực hiện cơ chế tương ứng | Transaction manager, rollback, version và cạnh tranh |
| Mapping | Dùng đối tượng Java đã có sẵn | Constructor, converter, entity/document và dữ liệu lưu thật |

Ví dụ, `.filter(Customer::active)` không đi qua cơ chế derived query. Nó không chứng minh một phương thức repository tên `findByActiveTrue` sẽ được module nhận diện đúng.

Tương tự, việc `PageImpl` trả về tổng số chính xác trong bộ nhớ không cho biết store sẽ phát bao nhiêu truy vấn hoặc truy vấn đếm nhanh đến đâu.

## 12. Thêm adapter dùng store thật mà không đổi phần ứng dụng

Khi cần thực hành tích hợp, giữ nguyên `CustomerCatalog` và `CustomerReader`, rồi thêm một adapter:

```text
CustomerCatalog
    -> CustomerReader
        -> adapter của store
            -> repository do Spring Data tạo
                -> entity hoặc document được mapping
                    -> driver và kho dữ liệu
```

Adapter chịu trách nhiệm:

1. Gọi thao tác đọc mà repository thực hỗ trợ.
2. Ánh xạ tên thuộc tính dùng trong phân trang/sắp xếp nếu mô hình persistence khác mô hình ứng dụng.
3. Chuyển kết quả persistence sang `Customer`.
4. Bảo toàn thông tin trang cần thiết.
5. Đáp ứng hoặc công khai giới hạn liên quan đến hợp đồng đã chọn.

Ví dụ, repository của adapter có thể khai báo phương thức `findByActiveTrue(Pageable pageable)` nếu module hỗ trợ derived query và kiểu trả về đó. Entity hoặc document phía sau có các thuộc tính phù hợp với mapping của module.

Không gắn annotation của nhiều store vào cùng một kiểu chỉ để tạo cảm giác có thể chuyển đổi tự động. Một mô hình dùng chung có thể phù hợp với vài trường hợp, nhưng không thay thế việc đánh giá yêu cầu mapping của từng công nghệ.

### 12.1. Đặt cấu hình kết nối ở ranh giới tích hợp

Những chi tiết sau thuộc phần lắp ghép môi trường:

- Dependency store module và driver.
- URL, tên database hoặc schema.
- Nguồn credential theo môi trường.
- Repository scanning và mapping.
- Migration, index và dữ liệu khởi tạo.
- Transaction manager hoặc hạ tầng đặc thù nếu dùng.

Chúng không cần xuất hiện trong chữ ký `listActive` hoặc constructor của `CustomerCatalog`. Nơi tạo adapter và repository chịu trách nhiệm cung cấp các chi tiết này.

Trong ứng dụng Spring, cấu hình chọn bean có thể dùng profile hoặc cơ chế cấu hình phù hợp. Cần xác định rõ bean nào được dùng ở môi trường nào; không để nguồn giả vô tình được chọn cho một đường chạy cần dữ liệu thật.

### 12.2. Giữ lại fixture và kỳ vọng nghiệp vụ khi tích hợp

Có thể đưa cùng dữ liệu mẫu vào store rồi kiểm tra lại các kỳ vọng về lọc, nội dung trang và thứ tự. Cách làm này giúp đối chiếu hợp đồng ứng dụng giữa nguồn giả và adapter.

Tuy nhiên, đối chiếu vài fixture không chứng minh hai nguồn tương đương trên mọi dữ liệu. Những trường hợp liên quan đến collation, `null`, thời gian, cạnh tranh hoặc giới hạn truy vấn phải được bổ sung theo yêu cầu thực tế.

## 13. Mở rộng ví dụ theo từng mục tiêu của Commons

### 13.1. Bổ sung CRUD

Nếu bài tiếp theo cần tạo khách hàng, hãy mô tả riêng hợp đồng ghi: ai cấp ID, điều gì xác định bản ghi mới, kết quả trả về mang trạng thái nào và lỗi trùng dữ liệu được xử lý ra sao.

Một `Map` trong bộ nhớ có thể phục vụ kiểm tra quy tắc ứng dụng, nhưng không tự đại diện cho semantics của `save`, merge, unique constraint hoặc optimistic locking. Khi adapter dùng `save` của repository, mã gọi nên sử dụng giá trị thực thể mà thao tác đó trả về theo hợp đồng.

Không triển khai hàng loạt phương thức ghi chưa được bài tập sử dụng chỉ để interface trông giống một repository đầy đủ.

### 13.2. Bổ sung projection

Hiện tại `CustomerCard` được tạo sau khi đọc `Customer`. Nếu mục tiêu chuyển sang học projection của repository, tạo một phiên bản adapter sử dụng loại projection được module hỗ trợ, rồi so sánh kết quả đầu ra.

Tách câu hỏi “API cần trả trường nào?” khỏi “store có giảm dữ liệu đọc không?”. Câu hỏi đầu thuộc hợp đồng ứng dụng; câu hỏi sau cần kiểm tra truy vấn và implementation.

### 13.3. Bổ sung Query by Example

Có thể thêm bộ lọc khách hàng với probe và `ExampleMatcher` trong một bài riêng. Kiểm thử độc lập giúp xác nhận ứng dụng chọn trường nào, bỏ qua trường nào và cấu hình matcher nào.

Việc Example thực sự tìm đúng dữ liệu vẫn cần repository có hỗ trợ `QueryByExampleExecutor` và các phép so khớp tương ứng. Không viết một bộ lọc Java rồi gọi nó là implementation đầy đủ của Query by Example trên mọi store.

### 13.4. Bổ sung auditing và thời gian

Nếu logic ứng dụng cần thời gian hiện tại, có thể truyền `Clock` vào lớp sử dụng thời gian. Kiểm thử dùng một `Clock` cố định để kết quả có thể dự đoán.

Đó là kỹ thuật kiểm tra logic thời gian của ứng dụng. Nó khác với việc module Spring Data tự điền `@CreatedDate`, `@LastModifiedDate`, `@CreatedBy` hoặc `@LastModifiedBy`.

Khi học auditing của Spring Data, cần bổ sung cấu hình auditing, nguồn thời gian/chủ thể phù hợp và một đường ghi thực tế đi qua cơ chế của module. Gán sẵn thời gian vào fixture không chứng minh callback auditing hoạt động.

## 14. Các lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách điều chỉnh |
| --- | --- | --- |
| Bắt đầu bằng toàn bộ application context | Lỗi môi trường che mất mục tiêu học abstraction | Khởi tạo trực tiếp phần logic không cần container |
| Đặt URL và credential trong service | Logic ứng dụng gắn chặt với môi trường | Đưa cấu hình vào nơi lắp ghép adapter |
| Nguồn giả luôn trả đúng một danh sách có sẵn | Bỏ sót lọc, sort hoặc page vẫn có thể không bị phát hiện | Dùng fixture có bản ghi inactive, tên trùng và thứ tự đầu vào khác kết quả |
| Phân trang trước khi lọc | Nội dung và tổng số sai hợp đồng truy vấn | Tính tập khớp trước khi cắt trang |
| Lấy kích thước trang làm tổng số | Điều hướng trang sai | Lấy tổng từ tập dữ liệu khớp điều kiện |
| Nhận `Sort` nhưng bỏ qua | Kiểm thử tạo niềm tin sai về thứ tự | Thực hiện hoặc từ chối rõ cách sắp xếp chưa hỗ trợ |
| Dùng dữ liệu ngẫu nhiên cho kỳ vọng cố định | Kết quả khó tái lập và khó giải thích | Tạo ID, tên và thời gian cố định khi phù hợp |
| Coi source trong bộ nhớ là repository thật | Suy diễn sai về truy vấn, transaction hoặc auditing | Giới hạn kết luận và thêm kiểm tra tích hợp đúng tính năng |
| Dùng DTO ứng dụng làm entity trên mọi store | Gặp giới hạn constructor hoặc mapping | Đánh giá mapping và tách mô hình persistence khi cần |

## 15. Bài tập tự kiểm tra

### Bài tập 1: tập dữ liệu không có khách hàng active

Tạo fixture chỉ có khách hàng inactive. Dự đoán nội dung, tổng số và tổng trang của kết quả trang đầu tiên. Kiểm tra rằng các thông tin này xuất phát từ tập khớp điều kiện chứ không phải số bản ghi ban đầu.

### Bài tập 2: đổi thứ tự ID của hai khách hàng cùng tên

Đảo vị trí hai bản ghi `An` trong danh sách nguồn. Kết quả mong muốn vẫn bắt đầu bằng `c-002`, rồi `c-004`. Nếu kết quả đổi theo thứ tự đầu vào, hãy xem lại khóa sắp xếp phụ.

### Bài tập 3: phân biệt chuyển đổi DTO với projection của repository

Giải thích vì sao `Page.map` tạo `CustomerCard` nhưng chưa chứng minh store chỉ đọc `id` và `name`. Nêu thêm một bằng chứng cần có khi adapter chuyển sang dùng projection tại repository.

### Bài tập 4: thêm một loại store

Phác thảo adapter mới mà không sửa `CustomerCatalog`. Liệt kê mapping, dependency và cấu hình nào thuộc adapter hoặc nơi lắp ghép. Xác định kỳ vọng nào có thể đối chiếu với fixture và kỳ vọng nào cần dữ liệu hoặc môi trường bổ sung.

### Bài tập 5: kiểm tra giới hạn kết luận

Giả sử toàn bộ kiểm thử độc lập đều đạt. Có thể kết luận những điều nào sau đây?

- Kích thước trang sai bị từ chối trước khi đọc dữ liệu.
- Store sử dụng đúng chỉ mục tối ưu cho `name` và `id`.
- `CustomerCard` có nội dung đúng với fixture.
- Auditing của store tự điền người sửa.
- Repository factory phân tích thành công mọi derived query của ứng dụng.

**Gợi ý trả lời:** Các kiểm thử đã minh họa có căn cứ cho quy tắc đầu vào và nội dung `CustomerCard` với fixture. Chỉ mục, auditing và việc tạo derived query chưa nằm trên đường chạy của chúng; cần kiểm tra qua adapter và module tương ứng.