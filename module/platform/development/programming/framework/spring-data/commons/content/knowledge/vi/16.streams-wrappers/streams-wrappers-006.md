# Vavr hoặc các collection khác theo khả năng hỗ trợ

## 1. Kiểu collection là một phần của hợp đồng repository

Một query method trả nhiều phần tử thường được khai báo bằng `List<T>`, `Collection<T>` hoặc `Iterable<T>`. Spring Data Commons còn có hạ tầng hỗ trợ một số kiểu kết quả khác, trong đó có collection của Vavr khi thư viện và khả năng tích hợp tương ứng hiện diện.

Điều cần hiểu không chỉ là “có thể thay List bằng kiểu nào”. Kiểu trả về còn diễn đạt các đặc tính mà người gọi dựa vào: có giữ phần tử trùng không, thứ tự có ý nghĩa không, có ánh xạ khóa–giá trị không, và thay đổi collection tạo ra kết quả mới hay sửa trực tiếp đối tượng cũ.

Trong phạm vi **SPRING_DATA_COMMONS**, cần tách ba bước:

```text
Kho dữ liệu thực thi query
    → ánh xạ từng kết quả thành entity hoặc projection
    → thích nghi tập kết quả sang kiểu collection được hỗ trợ
```

Khả năng thích nghi collection ở Commons không tự mở rộng mọi khả năng truy vấn của JPA, MongoDB, JDBC hoặc các mô-đun Spring Data khác. Một chữ ký Java hợp lệ về cú pháp vẫn có thể không được mô-đun hay phiên bản đang sử dụng hỗ trợ.

Bài học tập trung vào collection nhiều phần tử, cách sử dụng Vavr và cách chọn phương án thay thế khi chưa có hỗ trợ trực tiếp. Các ví dụ giả định dự án đã cấu hình repository và mapping phù hợp với kho dữ liệu của mình.

## 2. Vavr cung cấp điều gì?

Vavr là một thư viện cho Java, có các kiểu collection phục vụ cách lập trình hàm. Những collection như Vavr `List`, `LinkedHashSet` và `LinkedHashMap` là các cấu trúc dữ liệu bất biến theo hợp đồng của thư viện: thao tác cập nhật trả về một collection mới thay vì sửa collection đã có.

Ví dụ:

```java
import io.vavr.collection.List;
import io.vavr.collection.Seq;

Seq<String> original = List.of("An", "Bình");
Seq<String> expanded = original.append("Chi");

System.out.println(original.size()); // 2
System.out.println(expanded.size()); // 3
```

Việc gọi `append` mà bỏ qua giá trị trả về không làm `original` có thêm phần tử:

```java
original.append("Dũng"); // Kết quả mới bị bỏ qua.
```

Các cấu trúc persistent của Vavr có thể chia sẻ cấu trúc nội bộ giữa những phiên bản collection, thay vì luôn sao chép toàn bộ trong mọi thao tác. Từ “persistent” ở đây nói về cấu trúc dữ liệu giữ được phiên bản cũ; nó không có nghĩa thao tác collection tự ghi dữ liệu xuống database.

Cũng không đồng nhất bất biến của collection với bất biến của phần tử:

```java
Seq<Product> products = repository.findByCategoryOrderByNameAscIdAsc("BOOK");
Product first = products.head();
first.setName("Tên mới");
```

Collection không bị thêm hoặc xóa phần tử, nhưng đối tượng `Product` bên trong vẫn có thể thay đổi nếu model cho phép. Với entity được quản lý, ảnh hưởng của thay đổi này đối với kho dữ liệu thuộc hợp đồng của mô-đun, session và transaction, không do Vavr quyết định.

## 3. Các ánh xạ collection cần phân biệt

Khi tích hợp Vavr được hỗ trợ, Spring Data Commons có các ánh xạ đáng chú ý:

| Kiểu Vavr được khai báo | Triển khai Vavr dùng cho ánh xạ tương ứng | Nguồn Java thích hợp |
| --- | --- | --- |
| `io.vavr.collection.Seq<T>` | `io.vavr.collection.List<T>` | `java.lang.Iterable<T>` |
| `io.vavr.collection.Set<T>` | `io.vavr.collection.LinkedHashSet<T>` | `java.lang.Iterable<T>` |
| `io.vavr.collection.Map<K, V>` | `io.vavr.collection.LinkedHashMap<K, V>` | `java.util.Map<K, V>` |

Bảng này mô tả việc thích nghi kết quả, không phải lời hứa rằng mọi query method trên mọi kho dữ liệu đều có thể tạo mọi nguồn ở cột cuối.

Ba hệ quả quan trọng:

1. **`Seq` không có nghĩa là truy cập ngẫu nhiên kiểu ArrayList.** Triển khai tương ứng trong ánh xạ này là Vavr List, không phải tự động chọn Vector theo cách người gọi sử dụng.
2. **`Set` có thể làm giảm số phần tử.** Hai phần tử bằng nhau theo `equals` và `hashCode` không được giữ như hai phần tử riêng biệt của tập hợp.
3. **`Map` cần dữ liệu khóa–giá trị.** Một danh sách entity chưa tự trở thành map với khóa là `id` chỉ vì người viết đổi kiểu trả về.

Nên khai báo abstraction thể hiện đúng nhu cầu, chẳng hạn `Seq<Product>` nếu cần một chuỗi phần tử, thay vì để logic ứng dụng phụ thuộc vào một lớp triển khai cụ thể mà không cần thiết.

### 3.1. Trường hợp Traversable

Vavr `Traversable<T>` là abstraction rộng hơn. Khi kiểu này được hỗ trợ làm kết quả query, việc chọn triển khai có thể dựa trên hình dạng kết quả Java thực tế: nguồn dạng List phù hợp với Vavr List, nguồn Set phù hợp với LinkedHashSet, và nguồn Map phù hợp với LinkedHashMap.

Điều đó làm chữ ký linh hoạt nhưng kém cụ thể hơn đối với người gọi. Nếu nghiệp vụ cần giữ phần tử trùng và thao tác theo vị trí, hãy thể hiện bằng `Seq` thay vì chỉ dựa vào `Traversable`. Nếu nghiệp vụ cần tra cứu theo khóa, cần hợp đồng Map rõ ràng.

Không dùng kiểu rộng như một cách né giới hạn hỗ trợ của mô-đun. Nguồn kết quả vẫn phải được tạo và chuyển đổi đúng.

## 4. Điều kiện trước khi khai báo repository trả Vavr

Trước khi dùng trực tiếp, cần xác nhận các điểm sau trong dự án:

| Điều kiện | Vì sao cần |
| --- | --- |
| Có dependency Vavr trong classpath phù hợp | Java và framework phải nhận diện được các kiểu Vavr |
| Phiên bản Spring Data Commons có tích hợp cần dùng | Không suy khả năng của bản này từ một bản khác |
| Mô-đun kho dữ liệu hỗ trợ dạng query và kiểu kết quả liên quan | Commons không thay thế bộ thực thi query của mô-đun |
| Kết quả nguồn có thể thích nghi sang collection yêu cầu | Iterable và Map không diễn đạt cùng hình dạng dữ liệu |
| Mapping entity hoặc projection hợp lệ | Đổi collection không sửa được lỗi ánh xạ từng phần tử |

Dependency chính của thư viện là `io.vavr:vavr`. Phiên bản phải được chọn theo cấu hình dependency của dự án và mức tương thích đã xác nhận; không gán một số phiên bản tùy ý vào bài học rồi coi đó là yêu cầu chung của Commons.

Nếu dự án đang quản lý dependency bằng BOM hoặc dependency management, cần kiểm tra phiên bản thực sự được resolve. Việc mã biên dịch được chỉ chứng minh trình biên dịch nhìn thấy kiểu Vavr, chưa chứng minh query method đã được framework thực thi và chuyển đổi thành công.

## 5. Ví dụ dùng Seq cho kết quả nhiều sản phẩm

Giả sử entity `Product` đã được mapping với các thuộc tính:

| Thuộc tính | Kiểu minh họa | Vai trò |
| --- | --- | --- |
| `id` | `Long` | Định danh sản phẩm |
| `category` | `String` | Nhóm sản phẩm |
| `name` | `String` | Tên hiển thị |
| `price` | `BigDecimal` | Giá sản phẩm |

Trong mô-đun và phiên bản hỗ trợ, repository có thể khai báo:

```java
import io.vavr.collection.Seq;

import org.springframework.data.repository.Repository;

public interface ProductRepository extends Repository<Product, Long> {

    Seq<Product> findByCategoryOrderByNameAscIdAsc(String category);
}
```

`OrderByNameAscIdAsc` diễn đạt thứ tự query trong ví dụ. `id` là khóa phụ để những sản phẩm có tên trùng nhau vẫn có thứ tự rõ ràng. Khả năng phân tích và thực thi tên query phải được mô-đun hỗ trợ.

Service có thể xử lý kết quả theo API Vavr:

```java
import java.math.BigDecimal;
import java.util.Objects;

import io.vavr.collection.Seq;

public class ProductCatalog {

    private final ProductRepository repository;

    public ProductCatalog(ProductRepository repository) {
        this.repository = Objects.requireNonNull(repository);
    }

    public Seq<String> namesAtOrAbove(
            String category,
            BigDecimal minimumPrice) {

        Objects.requireNonNull(category, "category");
        Objects.requireNonNull(minimumPrice, "minimumPrice");

        Seq<Product> products =
                repository.findByCategoryOrderByNameAscIdAsc(category);

        return products
                .filter(product ->
                        product.getPrice().compareTo(minimumPrice) >= 0)
                .map(Product::getName);
    }
}
```

Ví dụ giả định `price` khác `null` và các thuộc tính được đọc còn hợp lệ trong phạm vi truy cập dữ liệu của ứng dụng. Nếu là entity có lazy loading, cần quản lý transaction hoặc chuyển sang projection phù hợp.

Điều kiện giá được đặt trong service chỉ để minh họa `filter` và `map`. Nếu chỉ cần sản phẩm từ một mức giá trở lên, nên cân nhắc đưa điều kiện đó xuống query được mô-đun hỗ trợ để giảm số hàng phải lấy và chuyển đổi.

`filter` trên collection đã nhận không tự được dịch ngược thành điều kiện database.

### 5.1. Kết quả rỗng

Một query nhiều phần tử nên được dùng với hợp đồng collection rỗng khi không có kết quả, thay vì coi việc không tìm thấy dữ liệu là một collection `null`.

```java
Seq<Product> products =
        repository.findByCategoryOrderByNameAscIdAsc("UNKNOWN");

if (products.isEmpty()) {
    // Không có sản phẩm phù hợp.
}
```

Với một triển khai tùy chỉnh hoặc adapter tự viết, cần giữ hợp đồng này nhất quán. Không dùng `head()` nếu chưa biết chuỗi có phần tử; khi cần xử lý tùy chọn, có thể dùng `headOption()` của Vavr.

Collection rỗng chỉ nói có 0 phần tử, không nói query bị lỗi. Exception truy cập dữ liệu cần được xử lý theo hợp đồng riêng, không âm thầm chuyển tất cả thành collection rỗng.

## 6. Khi nào Set phù hợp?

Một biến thể khai báo, nếu được mô-đun hỗ trợ:

```java
import io.vavr.collection.Set;

import org.springframework.data.repository.Repository;

public interface ProductSetRepository extends Repository<Product, Long> {

    Set<Product> findByCategoryOrderByNameAscIdAsc(String category);
}
```

Sử dụng `Set` khi tính duy nhất theo quan hệ bằng nhau của phần tử là một phần của hợp đồng ứng dụng.

Cần phân biệt ba khái niệm:

| Khái niệm | Nơi quyết định |
| --- | --- |
| Loại hàng trùng bằng `DISTINCT` | Hệ thống truy vấn và cách ánh xạ của mô-đun |
| Loại phần tử trùng khi đưa vào Set | `equals` và `hashCode` của đối tượng Java |
| Thứ tự duyệt kết quả | Thứ tự nguồn cùng hợp đồng collection cụ thể |

Chuyển sang Set không tự yêu cầu database chạy `DISTINCT`. Một query có thể đã truyền nhiều hàng rồi mới bị giảm phần tử ở tầng collection, nên lượng dữ liệu đọc và số phần tử cuối cùng không nhất thiết bằng nhau.

LinkedHashSet giữ thứ tự chèn của nguồn, nhưng nó không tự tạo tiêu chí sắp xếp cho một query vốn chưa có thứ tự. Nếu thứ tự có ý nghĩa nghiệp vụ, phải xác định thứ tự query và chọn kiểu kết quả thể hiện đúng yêu cầu đó.

Cũng cần thận trọng với entity có `equals` hoặc `hashCode` phụ thuộc vào trạng thái có thể thay đổi. Collection bất biến không làm các thuộc tính bên trong entity bất biến; thay đổi các giá trị tham gia tính hash có thể làm hỏng giả định tra cứu tập hợp.

Không chọn Set chỉ để làm biến mất kết quả lặp mà chưa hiểu nguyên nhân. Kết quả lặp có thể do join, projection hoặc một lỗi truy vấn cần được giải quyết tại đúng tầng.

## 7. Map không phải cách viết tắt của “đánh chỉ mục theo id”

Chữ ký sau không đủ để định nghĩa khóa của map:

```java
// Không suy ra rằng framework tự dùng Product.id làm khóa.
io.vavr.collection.Map<Long, Product> findByCategory(String category);
```

Ngay cả khi query trả nhiều `Product`, phần khai báo trên không cho biết:

- Dữ liệu nguồn có thực sự là một `java.util.Map` hay chỉ là các hàng kết quả.
- Thuộc tính nào làm khóa.
- Cách giải quyết khi hai hàng có cùng khóa.
- Cách xử lý khóa hoặc giá trị không hợp lệ theo hợp đồng ứng dụng.

Khả năng chuyển một Java Map thành Vavr Map không đồng nghĩa query engine tự nhóm mọi tập kết quả thành Map. Nếu một API truy vấn cụ thể có hỗ trợ kết quả Map, phải kiểm tra chính xác ý nghĩa của Map đó; chẳng hạn map của một hàng theo tên cột khác với map nhiều entity theo id.

### 7.1. Xây dựng Map tường minh ở tầng ứng dụng

Khi muốn đánh chỉ mục sản phẩm theo id, có thể bắt đầu bằng một query trả Java List được mô-đun hỗ trợ:

```java
import java.util.List;

import org.springframework.data.repository.Repository;

public interface ProductRows extends Repository<Product, Long> {

    List<Product> findByCategoryOrderByNameAscIdAsc(String category);
}
```

Sau đó tạo Vavr Map với chính sách khóa rõ ràng:

```java
import java.util.Objects;

import io.vavr.collection.LinkedHashMap;
import io.vavr.collection.Map;

public class ProductIndex {

    private final ProductRows repository;

    public ProductIndex(ProductRows repository) {
        this.repository = Objects.requireNonNull(repository);
    }

    public Map<Long, Product> byId(String category) {
        Objects.requireNonNull(category, "category");

        java.util.List<Product> rows =
                repository.findByCategoryOrderByNameAscIdAsc(category);

        Map<Long, Product> indexed = LinkedHashMap.empty();

        for (Product product : rows) {
            Long id = Objects.requireNonNull(product.getId(), "product.id");

            if (indexed.containsKey(id)) {
                throw new IllegalStateException("Duplicate product id: " + id);
            }

            indexed = indexed.put(id, product);
        }

        return indexed;
    }
}
```

Ví dụ này chủ động từ chối khóa trùng. Một nghiệp vụ khác có thể chọn giữ giá trị đầu tiên, giữ giá trị cuối cùng hoặc nhóm thành nhiều giá trị, nhưng phải nói rõ chính sách thay vì vô tình ghi đè.

Lệnh `indexed = indexed.put(...)` cần giữ giá trị mới trả về. Không gán lại thì biến vẫn tham chiếu phiên bản Map trước thao tác cập nhật.

Đây là phép chuyển đổi trong ứng dụng, không phải yêu cầu framework tự hỗ trợ query method trả Map theo id.

## 8. Chuyển đổi tường minh khi chưa hỗ trợ trực tiếp

Nếu dự án chưa xác nhận khả năng trả Vavr trực tiếp từ repository, có thể giữ kiểu kết quả Java đã được mô-đun hỗ trợ rồi chuyển đổi ở ranh giới service:

```java
import io.vavr.collection.List;
import io.vavr.collection.Seq;

java.util.List<Product> rows =
        repository.findByCategoryOrderByNameAscIdAsc("BOOK");

Seq<Product> products = List.ofAll(rows);
```

Ở đây `repository` có hợp đồng như `ProductRows` ở phần trước. Đây là một phương án thay thế cho repository trả `Seq` trực tiếp, không phải hai phương thức cùng chữ ký chỉ khác return type trong cùng một interface.

Một số phép chuyển đổi tường minh:

| Nguồn đã có | Đích muốn dùng | Ví dụ |
| --- | --- | --- |
| Java Iterable | Vavr List hoặc Seq | `io.vavr.collection.List.ofAll(rows)` |
| Java Iterable | Vavr LinkedHashSet | `io.vavr.collection.LinkedHashSet.ofAll(rows)` |
| Java Map | Vavr LinkedHashMap | `io.vavr.collection.LinkedHashMap.ofAll(javaMap)` |
| Vavr Traversable | Java List | `values.toJavaList()` |

Chuyển từ Iterable sang Set có thể mất phần tử trùng. Chuyển từ collection sang Map cần thêm quy tắc xác định khóa nếu nguồn chưa phải map. Các phép chuyển đổi không tự biến đổi entity thành DTO và không tự sao chép sâu từng đối tượng.

Phương án adapter làm trách nhiệm rõ ràng: repository thực hiện truy vấn bằng kiểu đã được hỗ trợ; tầng ứng dụng chọn API collection phù hợp với nghiệp vụ.

Đổi kiểu Java sang Vavr vẫn có chi phí tạo cấu trúc collection mới. Với tập dữ liệu lớn, tại một thời điểm có thể tồn tại cả collection nguồn và đích; không coi chuyển đổi là miễn phí về bộ nhớ.

## 9. Tránh nhầm import và tên kiểu

Các tên giống nhau thường gây lỗi khó nhìn thấy trong review:

| Tên ngắn | Kiểu có thể bị nhầm |
| --- | --- |
| `List` | `java.util.List` và `io.vavr.collection.List` |
| `Set` | `java.util.Set` và `io.vavr.collection.Set` |
| `Map` | `java.util.Map` và `io.vavr.collection.Map` |
| `Stream` | `java.util.stream.Stream` và `io.vavr.collection.Stream` |

Ví dụ, một phương thức khai báo `List<Product>` có ý nghĩa khác nhau tùy import. Không chỉ đọc tên ngắn rồi kết luận đó là collection Java hoặc Vavr.

Khi một lớp cần dùng cả hai họ collection, có thể import kiểu dùng thường xuyên và viết tên đầy đủ cho kiểu còn lại:

```java
import io.vavr.collection.Seq;

java.util.List<Product> rows = loadRows();
Seq<Product> products = io.vavr.collection.List.ofAll(rows);
```

`loadRows()` trong đoạn này đại diện cho hàm trả Java List đã được triển khai trong ứng dụng.

Vavr Stream cũng không phải Java Stream. Không áp dụng hợp đồng `AutoCloseable` của `java.util.stream.Stream` chỉ vì kiểu Vavr có cùng tên ngắn. Việc repository thích nghi sang một collection Vavr không chứng minh rằng ứng dụng đang đọc qua cursor database với cơ chế streaming.

## 10. Collection không thay thế projection, phân trang hoặc sắp xếp

### 10.1. Projection quyết định hình dạng của mỗi phần tử

Giả sử mô-đun hỗ trợ interface projection:

```java
import java.math.BigDecimal;

public interface ProductSummary {
    Long getId();
    String getName();
    BigDecimal getPrice();
}
```

Repository có thể sử dụng kiểu collection kết hợp projection khi cả hai khả năng đều được hỗ trợ:

```java
Seq<ProductSummary> findByCategoryOrderByNameAscIdAsc(String category);
```

Projection xác định phần tử là `ProductSummary`; Seq xác định cách biểu đạt tập phần tử. Lỗi ánh xạ trường giá, alias hoặc thuộc tính projection không được sửa bằng cách đổi `List` thành `Seq`.

Nếu muốn trả dữ liệu bất biến và độc lập với persistence context, cần xem xét cả DTO hoặc projection và các giá trị mà chúng chứa. Chỉ đổi collection bao ngoài chưa đủ.

### 10.2. Page có metadata riêng

`Page<Product>` bao gồm nội dung cùng metadata phân trang. Một Seq chỉ biểu đạt chuỗi phần tử, không tự mang tổng số phần tử, số trang hoặc thông tin còn trang tiếp theo.

Nếu cần dùng Vavr cho nội dung của một trang:

```java
Page<Product> page = repository.findByCategory(category, pageable);

Seq<Product> content =
        io.vavr.collection.List.ofAll(page.getContent());

long totalElements = page.getTotalElements();
```

Đoạn này giả định repository có thêm query phân trang phù hợp:

```java
Page<Product> findByCategory(String category, Pageable pageable);
```

`Page` và `Pageable` thuộc `org.springframework.data.domain`. Nếu trả một response tùy chỉnh, cần chuyển tiếp metadata mà caller còn cần, thay vì giữ mỗi `content` rồi gọi đó là một trang đầy đủ.

Không đổi sang `Page<Seq<Product>>` với kỳ vọng framework tự thay collection nội dung của Page. Tham số generic của Page là kiểu **mỗi phần tử**; chữ ký đó mô tả trang có các phần tử là Seq. Quy tắc tương tự cần được hiểu khi kết hợp với Slice hoặc Window.

### 10.3. Thứ tự cần được xác định trước khi chuyển đổi

Seq giữ thứ tự của nguồn được chuyển vào, nhưng không tự làm query không có `ORDER BY` trở thành có thứ tự ổn định.

Sắp xếp lại trong ứng dụng cũng có thể khác sắp xếp của database vì collation, quy tắc chữ hoa–chữ thường hoặc cách xử lý giá trị thiếu. Nếu phân trang hay scrolling dựa vào thứ tự query, không thay thứ tự sau khi nhận dữ liệu rồi giả định metadata hoặc vị trí tiếp tục vẫn mô tả cùng hành trình đọc.

## 11. Không suy rộng hỗ trợ sang mọi collection

Một kiểu có thể implement `Iterable` hoặc `Collection` nhưng vẫn không phù hợp làm return type của query method.

Ví dụ, ứng dụng có thể muốn trả một collection của thư viện khác, một queue chuyên dụng hoặc một lớp collection tự viết. Chỉ việc lớp đó có phương thức `iterator()` hoặc constructor nhận collection chưa chứng minh Spring Data biết tạo đúng kiểu đó.

Cần phân biệt:

1. **Kiểu trả về đã được framework và mô-đun hỗ trợ.** Có cơ chế nhận diện, thực thi query và chuyển đổi tương ứng.
2. **Kiểu có thể tạo bằng API thư viện ở tầng ứng dụng.** Có thể cần adapter tường minh sau khi repository đã trả kết quả.
3. **Wrapper có hợp đồng tích hợp riêng.** Chẳng hạn wrapper dựa trên Streamable phải đáp ứng hợp đồng mà Spring Data hỗ trợ, chứ không được suy từ việc nó “giống collection”.

Không mặc định đăng ký một bộ chuyển đổi thuộc tính trong tầng mapping entity sẽ làm kiểu collection ngoài cùng của query method được hỗ trợ. Chuyển đổi thuộc tính lưu trữ và thích nghi return type của query là hai điểm mở rộng khác nhau.

Khi chưa có bằng chứng hỗ trợ trực tiếp, cách dễ kiểm soát là trả kiểu Java phù hợp rồi chuyển sang kiểu thư viện tại ranh giới ứng dụng.

## 12. Hiệu năng và tính bất biến cần hiểu đúng

### 12.1. Collection không đồng nghĩa với cursor

Đổi return type thành Seq không cam kết driver lấy từng hàng từ server. Một query có thể đã tạo Java List đầy đủ rồi mới được chuyển sang Vavr List.

Với hàng triệu phần tử, cần đánh giá giới hạn kết quả, phân trang, scrolling hoặc cơ chế streaming được mô-đun hỗ trợ. Chọn collection bất biến không tự làm bộ nhớ sử dụng trở thành hằng số.

### 12.2. Chi phí thao tác phụ thuộc cấu trúc dữ liệu

Abstraction Seq không bảo đảm mọi thao tác có cùng chi phí như ArrayList. Vavr List phù hợp với các thao tác của danh sách liên kết; truy cập chỉ số hoặc nối cuối lặp nhiều lần có thể không phù hợp với yêu cầu hiệu năng.

Nếu nghiệp vụ cần một cấu trúc khác, hãy chuyển đổi có chủ đích sang kiểu Vavr hoặc Java thích hợp sau khi đã nhận dữ liệu. Không giả định framework tự chọn cấu trúc tối ưu theo cách sử dụng tương lai.

### 12.3. Bất biến của container không cung cấp thread safety cho entity

Hai thread đọc cùng collection bất biến vẫn có thể cùng truy cập những entity mutable bên trong. Session, lazy proxy và transaction có thể có ràng buộc thread riêng.

Nếu cần trao đổi dữ liệu giữa các thread, cần thiết kế dữ liệu độc lập và trạng thái bất biến của phần tử, thay vì dựa riêng vào kiểu collection bao ngoài.

### 12.4. API bên ngoài có hợp đồng tuần tự hóa riêng

Không mặc định một serializer đã cấu hình cho Java List sẽ biểu diễn mọi kiểu Vavr thành JSON đúng như API mong muốn. Khả năng tuần tự hóa cần được xác nhận theo serializer và cấu hình thực tế.

Có thể giữ Vavr trong tầng nghiệp vụ rồi chuyển sang DTO response và collection được API quy định tại ranh giới trả dữ liệu. Cách này cũng tránh để lựa chọn thư viện nội bộ tự trở thành hợp đồng công khai ngoài dự kiến.

## 13. Cách lựa chọn theo yêu cầu

| Nhu cầu | Lựa chọn để cân nhắc | Điều phải kiểm tra |
| --- | --- | --- |
| Chuỗi kết quả giữ phần tử trùng và thứ tự nguồn | Vavr Seq | Hỗ trợ return type, thứ tự query, chi phí thao tác |
| Tập phần tử duy nhất theo equality Java | Vavr Set | `equals`, `hashCode`, phần tử bị gộp và thứ tự cần dùng |
| Tra cứu kết quả theo khóa nghiệp vụ | Vavr Map qua adapter hoặc cơ chế query được hỗ trợ | Nguồn Map, khóa, chính sách trùng và giá trị thiếu |
| Chưa rõ mô-đun hỗ trợ Vavr trực tiếp | Java List rồi chuyển đổi | Chi phí chuyển đổi và nơi giữ trách nhiệm adapter |
| Cần tổng số kết quả và metadata trang | Page rồi thích nghi nội dung khi cần | Không làm mất metadata hoặc đổi sai generic |
| Cần xử lý tập dữ liệu rất lớn | Cơ chế giới hạn, phân trang, scrolling hoặc stream phù hợp | Hỗ trợ của kho dữ liệu và vòng đời tài nguyên |
| Dùng collection của thư viện khác | Kiểm tra hỗ trợ hoặc chuyển đổi tường minh | Không suy từ việc implement Iterable |

Không có một kiểu collection tốt nhất cho mọi repository. Chọn kiểu dựa trên ý nghĩa dữ liệu và khả năng đã được xác nhận của hệ thống đang chạy.

## 14. Các lỗi thường gặp và ca kiểm chứng

| Tình huống | Sai lầm có thể có | Điều cần xác nhận |
| --- | --- | --- |
| Biên dịch được nhưng khởi tạo repository lỗi | Có dependency nhưng return type hoặc query không được hỗ trợ | Tích hợp framework, mô-đun và chữ ký thực tế |
| Đã gọi `append` hoặc `put` nhưng dữ liệu không đổi | Bỏ qua giá trị collection mới | Gán hoặc trả về kết quả cập nhật |
| Số phần tử giảm khi đổi sang Set | Các phần tử bị gộp theo equality | Nội dung, cardinality và hợp đồng duy nhất |
| Dữ liệu có thứ tự khác nhau giữa các lần gọi | Nguồn query thiếu thứ tự xác định | Sort ở tầng query và khóa phụ |
| Muốn Map theo id nhưng conversion thất bại | Nguồn chỉ là tập hàng, chưa có map | Tạo ánh xạ khóa–giá trị tường minh |
| Entity bên trong collection vẫn thay đổi | Chỉ container bất biến | Thiết kế phần tử, DTO và persistence context |
| Metadata phân trang biến mất | Chỉ chuyển nội dung sang Seq rồi bỏ Page | Metadata caller còn cần |
| Dùng sai API hoặc kiểu trong signature | Nhầm import Java và Vavr | Tên kiểu đầy đủ và kiểu runtime |
| Bộ nhớ tăng cao | Materialize nhiều dữ liệu hoặc giữ cả nguồn và đích | Khối lượng dữ liệu, pipeline và collection đang được giữ |

Khi tích hợp vào một dự án thực tế, nên có dữ liệu đại diện cho các trường hợp sau:

- Không có kết quả: nhận collection rỗng theo hợp đồng.
- Có một và nhiều kết quả: phần tử và thứ tự đúng như query yêu cầu.
- Có phần tử bằng nhau: Seq giữ được điều cần giữ, Set gộp theo chính sách mong muốn.
- Có khóa trùng khi lập Map: xử lý đúng chính sách, không ghi đè ngoài ý muốn.
- Có tên sản phẩm trùng: khóa phụ giữ thứ tự rõ ràng.
- Có projection: từng phần tử được ánh xạ đúng trước khi sử dụng collection.
- Có dữ liệu lớn: chi phí tạo collection và giới hạn kết quả chấp nhận được.
- Có chuyển đổi sang Java hoặc response DTO: nội dung và hợp đồng bên nhận vẫn đúng.

Một ví dụ dùng `List.of(...)` của Vavr trong bộ nhớ chỉ chứng minh API collection hoạt động. Nó không chứng minh query method thật được mô-đun hỗ trợ hoặc dữ liệu được ánh xạ đúng từ kho lưu trữ.

## 15. Tình huống tự đánh giá

### A. Muốn tự có Map theo id

Một lập trình viên đổi `List<Product>` thành `Map<Long, Product>` ở return type và kỳ vọng framework tự dùng `id` làm khóa.

Hãy chỉ ra thông tin còn thiếu. Thiết kế một adapter nêu rõ cách lấy khóa và cách xử lý khóa trùng.

### B. Đổi sang Set để xóa bản ghi trùng

Query join trả nhiều hàng liên quan đến cùng sản phẩm. Nhóm phát triển dùng Vavr Set để số lượng hiển thị nhỏ lại.

Phân biệt xử lý trùng ở tầng query với equality của đối tượng Java. Nêu các thông tin phải kiểm tra trước khi kết luận Set giải quyết đúng yêu cầu.

### C. Collection bất biến nhưng entity vẫn bị sửa

Service nhận `Seq<Product>`, lấy phần tử đầu rồi gọi setter. Người viết cho rằng điều này không thể tác động trạng thái vì Seq là bất biến.

Giải thích khác biệt giữa bất biến của container và của phần tử, cùng điều cần kiểm tra nếu Product đang được quản lý bởi persistence context.

### D. Có thư viện collection khác trong classpath

Một kiểu collection của thư viện khác implement Iterable. Lập trình viên khai báo trực tiếp kiểu đó trong repository và cho rằng Spring Data sẽ biết tạo nó.

Nêu các khả năng hỗ trợ cần xác minh và đề xuất phương án chuyển đổi tường minh nếu chưa có tích hợp trực tiếp.

### E. Dùng Page với Seq

Nhóm phát triển muốn giữ metadata phân trang nhưng đổi chữ ký thành `Page<Seq<Product>>` để nội dung dùng Vavr.

Giải thích ý nghĩa của generic trong chữ ký này. Đề xuất cách chuyển nội dung trang mà vẫn giữ metadata cần thiết.

### F. Dùng Seq cho mười triệu kết quả

Một job đổi Java List sang Vavr Seq và kỳ vọng không còn tăng bộ nhớ vì đang dùng lập trình hàm.

Chỉ ra những bước có thể vẫn materialize dữ liệu. Chọn chiến lược lấy dữ liệu cần đánh giá theo khả năng kho lưu trữ và yêu cầu xử lý.

## 16. Quy trình áp dụng

1. Xác định hợp đồng kết quả: chuỗi, tập hợp hay ánh xạ khóa–giá trị.
2. Kiểm tra kiểu return được Commons, mô-đun và phiên bản dự án hỗ trợ.
3. Xác định hình dạng kết quả nguồn trước khi chuyển đổi collection.
4. Giữ query, projection, sort và metadata đúng với yêu cầu dữ liệu.
5. Dùng Vavr trực tiếp khi đã xác nhận hỗ trợ, hoặc tạo adapter tường minh từ kiểu Java phù hợp.
6. Kiểm tra cardinality, equality, khóa trùng, dữ liệu rỗng và chi phí bộ nhớ.
7. Giữ ranh giới giữa collection nội bộ với DTO, transaction và hợp đồng API rõ ràng.

Collection Vavr giúp biểu đạt cách xử lý dữ liệu bất biến trong Java. Để dùng đúng trong Spring Data, lựa chọn đó phải đi cùng hiểu biết về kiểu kết quả nguồn và khả năng của từng mô-đun kho dữ liệu.