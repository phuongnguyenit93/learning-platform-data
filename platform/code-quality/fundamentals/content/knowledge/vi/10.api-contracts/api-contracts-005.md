# Quy ước null, Optional và collection rỗng

Một phương thức tìm khách hàng trả về `null`. Phương thức tìm đơn hàng lại trả về danh sách rỗng. Một phương thức khác trả về `Optional<Customer>`. Cả ba đều có thể biểu diễn tình huống không tìm thấy dữ liệu, nhưng mỗi kiểu khiến người gọi phải xử lý khác nhau. Nếu dự án không thống nhất quy ước, những dòng mã tưởng đơn giản có thể dẫn tới `NullPointerException`, bỏ qua lỗi hệ thống hoặc diễn giải sai dữ liệu nghiệp vụ.

Trong chương **Hợp đồng API** của module `CODE_QUALITY_FUNDAMENTALS`, chất lượng mã nguồn gắn với việc mã **đáng tin cậy, dễ hiểu và dễ thay đổi**. Hợp đồng API tốt trả lời rõ: dữ liệu nào có thể vắng mặt, khi vắng mặt có nghĩa gì, khi nào đó là lỗi và người gọi phải kiểm tra điều gì. `null`, `Optional` và collection rỗng đều là công cụ hợp lệ, nhưng chúng không có cùng ý nghĩa.

Sau bài học, bạn có thể:

- Phân biệt “không có một kết quả”, “không có phần tử nào”, “chưa được cung cấp” và “không truy xuất được vì lỗi”.
- Chọn kiểu trả về phù hợp giữa `T`, `Optional<T>`, `List<T>`, `Map<K, V>` và kiểu kết quả nghiệp vụ riêng.
- Xác định rõ khi nào tham số, phần tử collection và giá trị trả về được phép là `null`.
- Sử dụng `Optional` đúng cách với `ofNullable`, `map`, `flatMap`, `orElse` và `orElseGet`.
- Thiết kế collection rỗng, quyền chỉnh sửa và bản sao dữ liệu theo hợp đồng.
- Viết kiểm thử cho các nhánh vắng mặt, lỗi, dữ liệu rỗng và khả năng tương thích khi đổi API.

## 1. Hợp đồng API phải nói rõ “không có” nghĩa là gì

So sánh bốn tình huống trong hệ thống bán hàng:

1. Không tìm thấy khách hàng có mã `C-123`.
2. Khách hàng `C-123` tồn tại nhưng chưa có đơn hàng.
3. Hệ thống chưa thực hiện bước lấy lịch sử đơn hàng.
4. Database lịch sử đơn hàng đang lỗi nên không thể trả kết quả.

Bốn tình huống này khác nhau:

| Tình huống | Ý nghĩa | Cách biểu diễn thường hợp lý |
| --- | --- | --- |
| Tìm một khách hàng theo ID nhưng không thấy | Không có đối tượng phù hợp | `Optional<Customer>.empty()` ở API tra cứu |
| Tìm các đơn hàng của một khách hàng nhưng có 0 đơn | Truy vấn thành công, có 0 phần tử | `List<Order>` rỗng |
| Chưa chạy truy vấn | Kết quả chưa được xác định | Trạng thái chưa tải, kiểu kết quả riêng hoặc cơ chế thực thi bất đồng bộ |
| Truy vấn không thành công do lỗi | Không biết kết quả thực tế | Exception hoặc kiểu lỗi rõ ràng; không giả vờ trả danh sách rỗng |

Nếu mọi trường hợp đều trở thành `null`, người gọi buộc phải đoán nguyên nhân. Nếu lỗi database lại được đổi thành `List.of()`, màn hình có thể hiển thị “Khách chưa có đơn” dù dữ liệu thực tế chưa lấy được.

**Nguyên tắc:** trước khi chọn kiểu trả về, hãy phân biệt **kết quả hợp lệ nhưng vắng mặt** với **không thực hiện được thao tác**. Đó là khác biệt nghiệp vụ, không chỉ khác biệt cú pháp.

## 2. Vì sao null dễ tạo hợp đồng ngầm?

`null` là giá trị đặc biệt của kiểu tham chiếu trong Java, biểu diễn việc không có đối tượng tham chiếu tại vị trí đó. Nó không tự nói “không tìm thấy”, “chưa nhập”, “đã xóa” hay “bị lỗi”.

Ví dụ API chưa xác định rõ:

```java
Customer findCustomer(String customerId);
```

Một người gọi có thể viết:

```java
String name = repository.findCustomer("C-123").name();
```

Nếu phương thức trả `null` khi không tìm thấy, `name()` gây `NullPointerException`. Người gọi cần đọc tài liệu hoặc mã triển khai để biết có phải kiểm tra `null` hay không.

Việc có `null` trong API cũng làm những điểm gọi phải bổ sung logic phòng vệ, thường là:

```java
Customer customer = repository.findCustomer("C-123");
if (customer != null) {
    showCustomer(customer);
}
```

Cách này không sai khi **hợp đồng quy định rõ** rằng giá trị có thể null. Vấn đề là thiếu quy ước nhất quán, khiến người gọi quên kiểm tra hoặc tự suy diễn về ý nghĩa.

### null vẫn có trường hợp dùng hợp lý

Không cần cấm tuyệt đối `null`. Nó có thể xuất hiện ở ranh giới với thư viện cũ, JavaBeans, JDBC, JSON hoặc framework mà hợp đồng cho phép. Một tham số tùy chọn của API bên ngoài cũng có thể dùng null theo quy ước đã xác định.

Tuy nhiên, tại API do nhóm tự thiết kế, hãy tự hỏi: **người gọi có thể nhận ra sự vắng mặt từ chữ ký, kiểu trả về hoặc tài liệu ngay tại nơi dùng không?** Nếu không, cân nhắc mô hình rõ nghĩa hơn.

Trong Java, `Objects.requireNonNull(value, "value")` giúp từ chối đầu vào không được phép null ngay tại ranh giới, thay vì để lỗi xuất hiện xa nơi nhận dữ liệu.

## 3. Chọn T, Optional<T> hay collection dựa trên lực lượng kết quả

Một cách phân loại hữu ích là xem thao tác có thể trả về **bao nhiêu giá trị**:

| Kiểu trả về | Hợp đồng thường biểu diễn | Ví dụ |
| --- | --- | --- |
| `Customer` | Phải có đúng một đối tượng khi trả về bình thường | Tạo khách hàng thành công |
| `Optional<Customer>` | Có thể có 0 hoặc 1 đối tượng | Tra cứu theo ID |
| `List<Order>` | Có thể có 0, 1 hoặc nhiều phần tử | Liệt kê đơn hàng |
| `Map<String, Price>` | Có thể có 0 hoặc nhiều cặp khóa–giá trị | Bảng giá theo mã sản phẩm |
| Kiểu kết quả riêng | Nhiều trạng thái cần phân biệt hơn có/không | Đã tải, chưa tải, không đủ quyền, lỗi tạm thời |

Quy tắc này là điểm xuất phát, không phải luật tuyệt đối. Ví dụ, `Optional<List<Order>>` đôi khi có ý nghĩa nếu “chưa có danh sách” thật sự khác “danh sách đã có nhưng rỗng”. Nhưng nếu phương thức luôn thực hiện truy vấn và trả 0 hoặc nhiều kết quả, `List<Order>` thường đơn giản và rõ hơn.

### Chữ ký cho hai kiểu câu hỏi khác nhau

```java
interface CustomerRepository {
    Optional<Customer> findById(CustomerId id);

    List<Customer> findByCity(String city);
}
```

`findById` trả 0 hoặc 1 khách hàng. `findByCity` có thể tìm thấy 0, 1 hoặc nhiều người. Người gọi được hướng dẫn bằng chính kiểu dữ liệu:

```java
Optional<Customer> maybeCustomer = repository.findById(id);

List<Customer> customersInCity = repository.findByCity("Đà Nẵng");
for (Customer customer : customersInCity) {
    showCustomer(customer);
}
```

Vòng `for` chạy 0 lần khi danh sách rỗng, không cần kiểm tra null trước. Còn `Optional` buộc người gọi cân nhắc trường hợp vắng mặt khi cần sử dụng đối tượng.

## 4. Ví dụ Java: hợp đồng nhất quán trong một repository

Giả sử dùng Java 17 với dữ liệu khách hàng đơn giản:

```java
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;

record CustomerId(String value) {
    CustomerId {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Customer ID is required");
        }
    }
}

record Customer(CustomerId id, String name, String city) {
    Customer {
        Objects.requireNonNull(id, "id");
        Objects.requireNonNull(name, "name");
        Objects.requireNonNull(city, "city");
    }
}

interface CustomerRepository {
    Optional<Customer> findById(CustomerId id);
    List<Customer> findByCity(String city);
}

final class InMemoryCustomerRepository implements CustomerRepository {
    private final Map<CustomerId, Customer> customers;

    InMemoryCustomerRepository(Map<CustomerId, Customer> customers) {
        this.customers = Map.copyOf(customers);
    }

    @Override
    public Optional<Customer> findById(CustomerId id) {
        Objects.requireNonNull(id, "id");
        return Optional.ofNullable(customers.get(id));
    }

    @Override
    public List<Customer> findByCity(String city) {
        Objects.requireNonNull(city, "city");
        return customers.values().stream()
                .filter(customer -> customer.city().equals(city))
                .toList();
    }
}
```

Hợp đồng của ví dụ:

- `findById` **không trả null**: không có ID phù hợp thì nhận `Optional.empty()`.
- `findByCity` **không trả null**: không có người ở thành phố đó thì nhận `List` rỗng.
- Tham số `id` và `city` không được null; `Objects.requireNonNull` từ chối sớm bằng `NullPointerException` có thông tin tham số.
- `Map.copyOf` tạo map không thể sửa qua API map và từ chối key/value null; các record ở ví dụ không cho phép các trường thành phần null.
- `Stream.toList()` trong Java 17 trả danh sách không thể chỉnh sửa qua các thao tác như `add`; `List` có thể rỗng.

Ví dụ minh họa hợp đồng **trong bộ nhớ**. Một repository thật còn cần xử lý lỗi kết nối, timeout, phân trang và tính nhất quán của dữ liệu. Nếu database thất bại, nó không nên tự chuyển lỗi thành `Optional.empty()` hoặc `List.of()` vì khi đó người gọi không thể phân biệt “không có dữ liệu” và “không lấy được dữ liệu”.

## 5. Optional: vắng mặt là một nhánh hợp lệ của kết quả

`Optional<T>` là một container có thể chứa **một đối tượng không null** hoặc không chứa giá trị nào. Nó đặc biệt hữu ích cho kiểu tra cứu 0 hoặc 1 kết quả:

```java
Optional<Customer> customer = repository.findById(customerId);
```

Điều quan trọng không phải là “bọc giá trị cho có”, mà là **làm trường hợp vắng mặt trở nên hiển thị** ở chữ ký.

### Các cách tạo Optional

```java
Optional<String> name = Optional.of("Mai");       // Có giá trị.
Optional<String> missing = Optional.empty();       // Không có giá trị.
Optional<String> fromApi = Optional.ofNullable(rawName);
```

- `Optional.of(value)` yêu cầu `value` khác null; truyền null gây `NullPointerException`.
- `Optional.ofNullable(value)` trả `Optional.empty()` khi `value == null`.
- `Optional.empty()` biểu diễn có chủ đích trường hợp không có giá trị.

Đừng viết một phương thức khai báo trả `Optional<Customer>` nhưng đôi khi `return null`. Làm vậy phá vỡ chính hợp đồng mà `Optional` muốn biểu diễn:

```java
// Sai hợp đồng: kết quả Optional vẫn có thể là null.
Optional<Customer> findById(CustomerId id) {
    return null;
}
```

Người gọi có thể bị `NullPointerException` ngay ở lời gọi `findById(id).map(...)`, dù đã tin rằng vắng mặt được biểu diễn bằng `Optional.empty()`.

### Dùng Optional theo ý định của người gọi

Khi vắng mặt là bình thường, có thể dùng:

```java
repository.findById(id)
        .ifPresent(this::showCustomer);
```

Khi cần giá trị mặc định:

```java
String displayName = repository.findById(id)
        .map(Customer::name)
        .orElse("Khách không xác định");
```

Khi bắt buộc phải có đối tượng:

```java
Customer customer = repository.findById(id)
        .orElseThrow(() -> new IllegalArgumentException(
                "Customer not found: " + id.value()));
```

Ví dụ cuối cho thấy **chính sách của người gọi** quyết định việc không tìm thấy có phải lỗi trong ngữ cảnh đang xử lý hay không. Tầng repository mô tả sự thật “0 hoặc 1 kết quả”; tầng nghiệp vụ quyết định có từ chối thao tác khi không có kết quả hay không.

Không nên dùng `optional.get()` mà chưa bảo đảm có giá trị; khi rỗng, `get()` ném `NoSuchElementException`. Trong phần lớn trường hợp, `map`, `ifPresent`, `orElse`, `orElseGet` hoặc `orElseThrow` diễn đạt ý định rõ hơn.

## 6. map, flatMap và điểm dễ nhầm khi xử lý Optional

Giả sử `Customer` có tên không null và cần chuyển sang chữ hoa:

```java
Optional<String> upperName = repository.findById(id)
        .map(Customer::name)
        .map(String::toUpperCase);
```

Nếu không tìm thấy khách hàng, kết quả cuối là `Optional.empty()`; các phép biến đổi không chạy. Nếu `map` trả về null, `Optional.map` chuyển kết quả đó thành `Optional.empty()` theo hợp đồng Java. Vì vậy, **đừng dựa vào một mapper trả null để báo lỗi hệ thống**: lỗi có thể bị hiểu thành vắng mặt bình thường.

Khi hàm biến đổi **đã trả về Optional**, dùng `flatMap` để tránh container lồng nhau:

```java
Optional<String> preferredName(Customer customer) {
    String name = customer.name().trim();
    return name.isEmpty() ? Optional.empty() : Optional.of(name);
}

Optional<String> name = repository.findById(id)
        .flatMap(this::preferredName);
```

`map(this::preferredName)` sẽ tạo `Optional<Optional<String>>`. `flatMap` kết hợp hai bước vắng mặt thành một `Optional<String>`.

Lưu ý: với `flatMap`, hàm ánh xạ phải **trả về một Optional khác null**. Nếu mapper trả null, phương thức ném `NullPointerException`. Cách biểu diễn rõ về vắng mặt giúp tránh các quy ước ngầm giữa các hàm.

### orElse khác orElseGet ở thời điểm tính mặc định

```java
Customer customer = repository.findById(id)
        .orElse(createGuestCustomer());
```

Đối số `createGuestCustomer()` **được tính trước** khi `orElse` chạy, kể cả khi đã tìm thấy khách. Nếu việc tạo khách tạm tốn tài nguyên hoặc có tác dụng phụ, kết quả có thể bất ngờ.

Khi muốn chỉ tạo mặc định nếu thật sự rỗng:

```java
Customer customer = repository.findById(id)
        .orElseGet(this::createGuestCustomer);
```

`orElseGet` nhận một `Supplier` và chỉ gọi nó khi không có giá trị. Hai lựa chọn có thể cho ra cùng dữ liệu khi mặc định là hằng số rẻ, nhưng **khác nhau về thời điểm và chi phí tính toán**.

## 7. Optional có giới hạn: không dùng để che lỗi và trạng thái khác nhau

`Optional.empty()` chỉ biểu diễn “không có giá trị”; nó không nói nguyên nhân. Xét ba kết quả của một yêu cầu lấy báo giá:

- Chưa tính vì người dùng chưa nhập địa chỉ.
- Địa chỉ không nằm trong vùng hỗ trợ.
- Dịch vụ hãng vận chuyển đang lỗi.

Nếu cả ba thành `Optional.empty()`, giao diện không biết nên yêu cầu nhập địa chỉ, báo không hỗ trợ hay đề nghị thử lại.

Có thể dùng một kiểu kết quả riêng khi các trạng thái này là một phần của hợp đồng:

```java
sealed interface QuoteResult
        permits QuoteAvailable, AddressRequired, UnsupportedRegion {}

record QuoteAvailable(long feeVnd) implements QuoteResult {
    QuoteAvailable {
        if (feeVnd < 0) {
            throw new IllegalArgumentException("Fee cannot be negative");
        }
    }
}

record AddressRequired() implements QuoteResult {}

record UnsupportedRegion(String region) implements QuoteResult {
    UnsupportedRegion {
        if (region == null || region.isBlank()) {
            throw new IllegalArgumentException("Region is required");
        }
    }
}
```

Người gọi có thể phân biệt ba kết quả nghiệp vụ. Một lỗi hạ tầng như timeout có thể được báo qua exception hoặc một biến thể lỗi riêng nếu hợp đồng yêu cầu phục hồi theo kiểu kết quả. **Không nên tự thêm `QuoteAvailable(0)` cho lỗi mạng**: phí bằng 0 có thể là báo giá thật, khác hoàn toàn với việc chưa lấy được báo giá.

Cũng không cần tạo sealed hierarchy cho mọi thao tác đơn giản. Nếu chỉ có “tìm thấy/không thấy”, `Optional<T>` đã là biểu đạt gọn và đủ nghĩa.

## 8. Vì sao collection rỗng thường tốt hơn null?

Một API trả về nhiều phần tử nên cho phép người gọi lặp trực tiếp trên kết quả:

```java
List<Order> orders = orderRepository.findByCustomer(customerId);

for (Order order : orders) {
    render(order);
}
```

Khi không có đơn hàng, `orders` là danh sách rỗng; vòng lặp tự chạy 0 lần. Nếu API trả `null`, tất cả người gọi phải kiểm tra trước:

```java
if (orders != null) {
    for (Order order : orders) {
        render(order);
    }
}
```

Kiểm tra null lặp lại làm code dài và mở ra nguy cơ quên kiểm tra. Nó còn khiến `null` trở thành một trạng thái mà phần lớn người gọi không cần phân biệt với 0 phần tử.

Một hợp đồng hữu ích cho phương thức tìm nhiều kết quả:

> Trả một collection không null. Nếu truy vấn thành công mà không có phần tử, trả collection rỗng. Nếu không thể thực hiện truy vấn, báo lỗi theo hợp đồng riêng.

### Optional<List<T>> có cần thiết không?

Với phương thức `findOrdersByCustomer` luôn thực hiện truy vấn, `Optional<List<Order>>` thường thêm một nhánh không cần thiết:

```java
Optional<List<Order>> findOrdersByCustomer(CustomerId id);
```

Người gọi phải hỏi cả “có danh sách không?” lẫn “danh sách có phần tử không?”, trong khi một danh sách rỗng có thể đã biểu diễn đúng 0 đơn.

Tuy nhiên, `Optional<List<Order>>` có thể có nghĩa khi **thực sự có hai trạng thái cần phân biệt**: chưa truy vấn và đã truy vấn nhưng rỗng. Hãy ghi rõ ý nghĩa đó; với API công khai lâu dài, một kiểu trạng thái như `NotLoaded`/`Loaded(List<Order>)` có thể diễn đạt dễ hiểu hơn.

Một biểu đồ chọn kiểu:

```text
Kết quả thành công có bao nhiêu phần tử?
        |
        +-- Đúng 1 --------------> T (hoặc lỗi nếu không thể có)
        |
        +-- 0 hoặc 1 ------------> Optional<T>
        |
        +-- 0 đến nhiều ---------> Collection<T> không null
        |
        +-- Có nhiều trạng thái
            ngoài số lượng ------> Kiểu kết quả miền rõ nghĩa
```

## 9. Collection rỗng: cùng nội dung, khác hợp đồng về khả năng sửa

Trong Java, nhiều cách tạo danh sách rỗng cho cùng một nội dung nhưng có hành vi khác nhau:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

List<String> a = List.of();
List<String> b = Collections.emptyList();
List<String> c = new ArrayList<>();
```

| Cách tạo | Có thể thêm phần tử qua API danh sách? | Phù hợp khi |
| --- | --- | --- |
| `List.of()` | Không | Trả kết quả rỗng không cho người gọi chỉnh sửa |
| `Collections.emptyList()` | Không | Trả collection rỗng, hỗ trợ API Java lâu đời |
| `new ArrayList<>()` | Có | Người gọi cần chủ động xây dựng hoặc sửa danh sách |

`List.of()` và `Collections.emptyList()` tạo danh sách rỗng không thể chỉnh sửa; một lời gọi `add` sẽ ném `UnsupportedOperationException`. `new ArrayList<>()` là danh sách có thể thay đổi. Nếu API không cho người gọi sửa dữ liệu nội bộ, trả một danh sách không thể chỉnh sửa thường là lựa chọn an toàn hơn.

### Tránh để người gọi sửa trạng thái của đối tượng sở hữu

Xét lớp giữ danh sách đơn:

```java
final class OrderHistory {
    private final List<Order> orders = new ArrayList<>();

    List<Order> getOrders() {
        return orders; // Rò rỉ danh sách nội bộ có thể sửa.
    }
}
```

Người gọi có thể `getOrders().clear()` và xóa dữ liệu bên trong đối tượng mà không đi qua quy tắc nghiệp vụ. Nếu muốn chỉ cung cấp một bản chụp danh sách:

```java
final class OrderHistory {
    private final List<Order> orders = new ArrayList<>();

    List<Order> getOrders() {
        return List.copyOf(orders);
    }
}
```

`List.copyOf` trả danh sách không thể sửa qua API và loại bỏ khả năng người gọi thay đổi cấu trúc danh sách nguồn thông qua kết quả trả về. Nó cũng **từ chối phần tử null**. Đây là bản sao nông: nếu bản thân các `Order` có trạng thái mutable, người gọi vẫn có thể tác động vào từng đối tượng bên trong nếu API của chúng cho phép.

Nếu hợp đồng cần một **view sống** phản ánh thay đổi của danh sách gốc, hoặc người gọi được phép chỉnh sửa, đó là thiết kế khác và phải được tài liệu hóa. Không nên mặc định “List là mutable” hay “List luôn immutable” chỉ nhìn vào kiểu `List<T>`.

## 10. Collection chứa null: ranh giới dễ bị bỏ quên

Việc trả về một danh sách không null **không có nghĩa phần tử bên trong đều không null**:

```java
List<String> names = new ArrayList<>();
names.add("An");
names.add(null);
```

Người gọi:

```java
for (String name : names) {
    System.out.println(name.toUpperCase());
}
```

sẽ gặp `NullPointerException` ở phần tử null.

Hợp đồng cần phân biệt hai tầng:

1. **Collection có thể null không?**
2. **Phần tử trong collection có thể null không?**

Nếu danh sách không cho phép phần tử null, hãy thực thi quy ước ở nơi tạo dữ liệu, chẳng hạn dùng `List.of` hoặc `List.copyOf`, cả hai đều từ chối phần tử null. Nếu nullable element thật sự có ý nghĩa, hãy làm rõ cách người gọi xử lý hoặc cân nhắc kiểu phần tử biểu diễn ý nghĩa vắng mặt.

Tương tự, `Map<K,V>` cần quy ước cho key và value null. `Map.of` và `Map.copyOf` từ chối key/value null. Không nên giả định mọi `Map` đều có quy tắc giống vậy: `HashMap` có thể chứa key và value null.

### Map.get và sự mơ hồ giữa key không tồn tại với value null

`Map.get(key)` trả null khi không có ánh xạ, nhưng với map cho phép value null, nó cũng trả null khi key **có tồn tại và được gán null**:

```java
Map<String, String> profile = new java.util.HashMap<>();
profile.put("phone", null);

System.out.println(profile.get("phone")); // null
System.out.println(profile.get("email")); // null
```

Nếu cần phân biệt, sử dụng `containsKey`:

```java
boolean phoneProvided = profile.containsKey("phone"); // true
boolean emailProvided = profile.containsKey("email"); // false
```

Ngoài ra, `Map.getOrDefault` chỉ dùng giá trị mặc định khi key **không có ánh xạ**; nếu key hiện diện và được ánh xạ tới null, nó có thể trả null. Khi dự án không cho phép value null, tránh đưa tình huống mơ hồ vào cấu trúc dữ liệu ngay từ đầu.

## 11. Quy ước null cho tham số đầu vào

Một tham số có được null hay không nên là một phần của API. So sánh:

```java
void updatePhone(CustomerId id, String phone);
```

Nếu `phone == null`, API dự định làm gì?

- Xóa số điện thoại hiện có?
- Không cập nhật trường này?
- Trả lỗi đầu vào?
- Đặt số điện thoại thành trạng thái chưa biết?

Bốn hành vi khác nhau không nên bị gộp vào một quy ước ngầm. Một API có thể tách thao tác:

```java
void changePhone(CustomerId id, String newPhone);
void clearPhone(CustomerId id);
```

Chữ ký `clearPhone` diễn đạt trực tiếp ý định xóa; `changePhone` có thể yêu cầu `newPhone` khác null và phù hợp định dạng nghiệp vụ.

Khi API cần gộp thao tác, có thể định nghĩa kiểu biểu diễn hành động, thay vì dùng null để chứa cả “giữ nguyên” và “xóa”:

```java
sealed interface PhoneChange
        permits KeepPhone, ClearPhone, SetPhone {}

record KeepPhone() implements PhoneChange {}

record ClearPhone() implements PhoneChange {}

record SetPhone(String value) implements PhoneChange {
    SetPhone {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Phone is required");
        }
    }
}
```

Bây giờ, `KeepPhone`, `ClearPhone` và `SetPhone` là ba yêu cầu phân biệt được bằng kiểu. Cấu trúc này hợp lý nếu phân biệt ba trạng thái là yêu cầu thực; với một API chỉ thay số điện thoại đơn giản, hai phương thức có tên rõ có thể dễ hiểu hơn.

### Optional có nên là tham số không?

Có thể viết `updatePhone(id, Optional<String> phone)`, nhưng người gọi phải tạo `Optional` ở từng nơi, và bản thân tham số kiểu `Optional` vẫn có thể bị truyền `null`. Theo thực hành phổ biến trong Java, `Optional` phù hợp nhất cho **kết quả trả về 0 hoặc 1**; với tham số, overload, phương thức có tên rõ hoặc kiểu yêu cầu chuyên biệt thường dễ dùng hơn.

Đó là hướng dẫn thiết kế, không phải quy định ngôn ngữ. Nếu API đã xác định rõ lợi ích của `Optional` làm tham số, vẫn cần ghi rõ nó không được null và ý nghĩa của `Optional.empty()`.

## 12. Nullable annotation, tài liệu và kiểm tra ranh giới

Hệ kiểu Java thông thường không phân biệt `String` với “`String` chắc chắn không null” ở cấp ngôn ngữ. Những công cụ phân tích tĩnh có thể sử dụng annotation nullability, nhưng **tên annotation và mức thực thi tùy thư viện/công cụ**.

Ví dụ mô tả ý định ở mức tài liệu:

```java
/**
 * Finds a customer by ID.
 *
 * @param id non-null customer ID
 * @return non-null Optional; empty when no customer matches
 * @throws NullPointerException if id is null
 */
Optional<Customer> findById(CustomerId id);
```

Một dự án có thể áp dụng hệ annotation như `@Nullable`, `@NonNull` hoặc công cụ tương ứng để kiểm tra tĩnh. Nhưng đừng ngầm cho rằng thêm annotation là JVM tự chặn null ở runtime. Để bảo vệ ranh giới khi chạy, dùng validation có chủ đích và thông báo phù hợp.

### Fail fast đúng vị trí

```java
Customer getRequiredCustomer(CustomerId id) {
    Objects.requireNonNull(id, "id");
    return repository.findById(id)
            .orElseThrow(() -> new IllegalArgumentException(
                    "Customer does not exist: " + id.value()));
}
```

Ví dụ này phân biệt hai loại sai:

- `id == null`: vi phạm tiền điều kiện của API, bị từ chối ngay.
- `id` hợp lệ nhưng không tìm thấy khách: không thỏa yêu cầu nghiệp vụ “phải có khách”.

Trong hệ thống web, tầng HTTP có thể chuyển trường hợp thứ hai thành phản hồi phù hợp, chẳng hạn 404 tùy chính sách và yêu cầu bảo mật. Không nên để mỗi lớp tự suy ra và biến mọi lỗi thành null.

Nếu một trường nullable là hợp lệ, hãy ghi rõ ý nghĩa và kiểm thử nhánh đó; “fail fast” không có nghĩa là cấm tất cả giá trị vắng mặt.

## 13. Ranh giới JSON và HTTP: thiếu trường khác trường null và mảng rỗng

Hợp đồng trả về đối tượng Java và hợp đồng của JSON/HTTP có thể có quy ước khác nhau. Xét ba JSON:

```json
{}
```

```json
{"phone": null}
```

```json
{"phone": ""}
```

Đối với yêu cầu cập nhật một phần (PATCH), nhiều API cần phân biệt:

- Không có trường `phone`: giữ nguyên giá trị hiện tại.
- Có `"phone": null`: yêu cầu xóa, nếu hợp đồng cho phép.
- Có `"phone": ""`: chuỗi rỗng; có thể bị từ chối hoặc có ý nghĩa riêng.

Không nên mặc định mọi thư viện deserialize ba dạng này thành các ý nghĩa được giữ nguyên. Một DTO chỉ có `String phone` có thể khiến “thiếu trường” và “có trường null” đều trở thành Java `null`, nếu không cấu hình hoặc mô hình thêm trạng thái hiện diện.

Trong JSON, `[]` cũng khác `null`:

```json
{"orders": []}
```

biểu diễn danh sách có 0 phần tử, trong khi:

```json
{"orders": null}
```

không tự nói danh sách đã được truy vấn hay chưa. Hợp đồng API cần chọn một ý nghĩa nhất quán, đồng thời quy định khi nào trường có thể bị bỏ qua hoàn toàn.

### Ví dụ HTTP thông dụng

- `GET /customers/C-123` không tìm thấy: thường trả 404 theo hợp đồng tài nguyên.
- `GET /customers?city=Hue` truy vấn thành công nhưng không có kết quả: thường trả 200 với `[]`.
- Truy vấn thất bại vì dịch vụ backend không khả dụng: báo lỗi phù hợp, không trả 200 với `[]` để giả vờ không có dữ liệu.

Đây là những quy ước thiết kế phổ biến, **không phải** một kết quả HTTP bắt buộc duy nhất cho mọi hệ thống. Tài liệu OpenAPI/schema và kiểm thử hợp đồng phải thống nhất với khách hàng sử dụng API.

## 14. Kiểm thử hợp đồng cho vắng mặt, rỗng và lỗi

Một API có thể chạy đúng trong trường hợp có dữ liệu mà vẫn sai khi không có dữ liệu. Vì vậy, cần kiểm thử các nhánh đặc biệt:

| Tình huống | Hợp đồng mong đợi |
| --- | --- |
| Tìm ID hiện có | `Optional.of(customer)` |
| Tìm ID không tồn tại | `Optional.empty()`; không null |
| Tra danh sách có phần tử | Collection chứa những phần tử hợp lệ |
| Tra danh sách không có phần tử | Collection rỗng; không null |
| Truyền tham số null vào nơi cấm | Từ chối ngay, lỗi được xác định |
| Kết quả có phần tử null ở nơi cấm | Bị chặn trước khi trả về hoặc khi xây collection |
| Backend hỏng | Phát tín hiệu lỗi; không giả vờ kết quả rỗng |
| Người gọi tìm cách sửa danh sách chỉ đọc | Không thay đổi dữ liệu của bên sở hữu |

Ví dụ JUnit 5 kiểm tra repository trong bộ nhớ ở mục 4:

```java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import java.util.List;
import java.util.Map;

class CustomerRepositoryContractTest {
    private final CustomerId knownId = new CustomerId("C-1");
    private final Customer known =
            new Customer(knownId, "Lan", "Hà Nội");

    private final CustomerRepository repository =
            new InMemoryCustomerRepository(Map.of(knownId, known));

    @Test
    void returnsEmptyOptionalForUnknownId() {
        assertTrue(repository.findById(
                new CustomerId("missing")).isEmpty());
    }

    @Test
    void returnsNonNullEmptyListWhenNoCustomerMatches() {
        List<Customer> result = repository.findByCity("Huế");
        assertNotNull(result);
        assertTrue(result.isEmpty());
    }

    @Test
    void rejectsNullInput() {
        assertThrows(NullPointerException.class,
                () -> repository.findById(null));
    }

    @Test
    void returnedListIsNotModifiable() {
        List<Customer> result = repository.findByCity("Hà Nội");
        assertThrows(UnsupportedOperationException.class,
                () -> result.add(known));
    }
}
```

Những test này xác minh một số hợp đồng quan sát được: vắng mặt, rỗng, tiền điều kiện và khả năng sửa của collection. Ví dụ này không giả lập sự cố database; với repository dùng I/O thật, cần test tích hợp hoặc test tại ranh giới lỗi để xác nhận backend thất bại được báo đúng.

Không nên chỉ kiểm thử `result != null`. Một `Optional.empty()` có thể đúng, còn `List.of()` cũng có thể đúng, nhưng cần xác nhận ngữ nghĩa cho từng phương thức.

## 15. Thay đổi API: giữ tương thích và tránh chuyển nghĩa dữ liệu

Giả sử phương thức cũ:

```java
Customer findById(CustomerId id); // Trả null nếu không thấy.
```

Muốn đổi thành:

```java
Optional<Customer> findById(CustomerId id);
```

Đây là **thay đổi chữ ký nguồn**: những điểm gọi đang gán kết quả vào `Customer` sẽ không biên dịch. Trong các thư viện Java đã phát hành, thay đổi kiểu trả về của phương thức cũng có thể phá tương thích nhị phân với mã client đã biên dịch, vì method descriptor ở bytecode chứa kiểu trả về.

Một cách chuyển đổi có kiểm soát là thêm API mới rõ nghĩa, rồi dời các điểm gọi theo kế hoạch:

```java
Optional<Customer> findOptionalById(CustomerId id) {
    return Optional.ofNullable(findLegacyById(id));
}

/** @deprecated Use findOptionalById instead. */
@Deprecated
Customer findLegacyById(CustomerId id) {
    // Legacy behavior: null when absent.
    return legacyLookup(id);
}
```

Đoạn trên minh họa **lớp chuyển tiếp**: cần giữ hành vi cũ và chỉ thay từng nơi sử dụng. Trong triển khai thật, hàm `legacyLookup` và các adapter phải được xác định rõ; không tạo vòng gọi giữa hai phương thức. Sau khi client đã chuyển đổi, có thể lên kế hoạch bỏ API cũ theo chính sách phiên bản.

Đối với API trả collection, việc đổi từ `null` sang rỗng giúp người gọi đơn giản hơn nhưng **vẫn có thể thay đổi hành vi** của client vốn dùng null để biểu diễn “chưa tải”. Trước khi đổi phải xác định lý do null từng tồn tại và bổ sung trạng thái rõ nếu cần.

### Hợp đồng cần nhất quán xuyên các tầng

Nếu repository trả `Optional.empty()` cho “không thấy”, service trả 404 cho thao tác bắt buộc có dữ liệu, còn controller trả JSON `null` trong một ngữ cảnh khác, những chuyển đổi ấy có thể hợp lý nếu mỗi tầng có hợp đồng rõ.

Nguy hiểm xuất hiện khi cùng một ý nghĩa bị chuyển tùy tiện, chẳng hạn lỗi SQL thành empty, empty thành phí giao hàng 0 rồi phí 0 thành thông báo “miễn phí”. Tại mỗi ranh giới, hãy xác định chuyển đổi có giữ lại thông tin nghiệp vụ cần thiết không.

## 16. Những sai lầm thường gặp

**Trả null cho một phương thức khai báo `Optional<T>`.** Điều này phá hợp đồng và gây lỗi ở điểm gọi.

**Dùng `Optional.of(value)` khi `value` có thể null.** Phương thức sẽ ném `NullPointerException`; dùng `ofNullable` nếu null thật sự có nghĩa là không có kết quả.

**Gọi `get()` vô điều kiện trên Optional.** Khi rỗng sẽ ném `NoSuchElementException`; ưu tiên cách xử lý diễn đạt ý định rõ.

**Lạm dụng `Optional<List<T>>`.** Nếu truy vấn đã hoàn tất và chỉ có 0..n phần tử, collection rỗng thường đã diễn đạt đầy đủ.

**Trả `null` thay vì collection rỗng.** Điều này bắt mọi người gọi thêm nhánh kiểm tra, trừ khi null mang ý nghĩa riêng được định nghĩa rõ.

**Trả collection mutable nội bộ.** Người gọi có thể thay đổi trạng thái của bên sở hữu mà không qua kiểm tra nghiệp vụ.

**Cho phép phần tử null nhưng không nói rõ.** Collection không null vẫn có thể chứa null và gây lỗi khi lặp.

**Dùng `Optional.empty()` hoặc `List.of()` để che lỗi.** Không tìm thấy hợp lệ khác với không thể truy xuất; cần giữ thông tin về lỗi.

**Dùng null để gộp “không gửi” và “xóa”.** Với cập nhật một phần, phải phân biệt trường không có mặt với trường được gửi null nếu nghiệp vụ cần.

**Tin rằng Optional hoặc annotation tự xử lý nhất quán dữ liệu.** Chúng không thay thế transaction, kiểm soát đồng thời, validation nghiệp vụ hay hợp đồng lỗi giữa các hệ thống.

## 17. Bài tập tình huống

### Tình huống A: danh sách lịch sử đơn hàng

Một API trả `null` khi khách chưa mua gì, còn trả `List<Order>` khi có đơn. Màn hình đang kiểm tra `null` để hiển thị “Chưa có đơn hàng”.

Bạn sẽ sửa hợp đồng thành `List<Order>` luôn không null hay giữ null với ý nghĩa riêng? Hãy mô tả nơi phải sửa, các test cho danh sách rỗng và cách phân biệt nếu truy vấn database thất bại.

### Tình huống B: tìm số điện thoại

Hàm `findPhone(CustomerId id)` có thể gặp ba trường hợp: có số, khách tồn tại nhưng không có số và khách không tồn tại.

`Optional<String>` có biểu diễn đủ thông tin nếu người gọi cần phân biệt hai trường hợp cuối không? Hãy đề xuất một kiểu kết quả hoặc cách tra cứu gồm hai bước, và nêu rủi ro khi dùng `null` cho cả hai.

### Tình huống C: đồng bộ hồ sơ

Yêu cầu JSON gửi `{"phone": null}` để xóa số điện thoại; bỏ hẳn trường `phone` để giữ nguyên. Nhưng DTO dùng `String phone` nên hai yêu cầu đều thành `null`.

Hãy xác định thông tin nào bị mất ở bước deserialize. Đề xuất cách giữ trạng thái có mặt/vắng mặt và kiểm thử cả JSON rỗng, trường null, trường có chuỗi.

### Tình huống D: danh sách không thể sửa

Một phương thức trả trực tiếp `ArrayList<Order>` nội bộ. Một client gọi `clear()` để dọn dữ liệu hiển thị và vô tình xóa lịch sử bên trong service.

Hãy đề xuất cách trả kết quả phù hợp và giải thích giới hạn của bản sao nông nếu `Order` là đối tượng mutable.

### Tình huống E: lỗi ẩn dưới kết quả rỗng

Một repository bắt mọi `SQLException` rồi trả `Optional.empty()`. Nhờ đó controller hiếm khi trả lỗi, nhưng nhiều khách hàng bị hiển thị “không tồn tại” khi database mất kết nối.

Hãy xác định hợp đồng bị vi phạm, cách phân biệt trạng thái không tìm thấy với lỗi hạ tầng và test cần bổ sung.

## 18. Ghi nhớ

Một quy ước tốt giúp người sử dụng API phân biệt được **dữ liệu có mặt hay không**, **có bao nhiêu phần tử**, **vì sao thao tác thất bại** và **ai được phép chỉnh sửa kết quả**.

- `T` thường phù hợp khi thao tác thành công luôn có một giá trị.
- `Optional<T>` phù hợp khi 0 hoặc 1 kết quả là tình huống hợp lệ; bản thân Optional không được null.
- Collection thường nên không null và trả rỗng khi truy vấn thành công với 0 phần tử.
- Cần làm rõ cả collection có null hay không, phần tử có null hay không và collection có thể sửa hay không.
- `null` có thể là quy ước hợp lệ tại một số ranh giới, nhưng phải có ý nghĩa rõ; tránh dùng nó để gộp thiếu dữ liệu, chưa tải và lỗi.
- `Optional.empty()` và collection rỗng không được dùng để che lỗi truy xuất.
- Những trạng thái nghiệp vụ khác nhau cần kiểu, hợp đồng hoặc giao thức phân biệt được; đặc biệt với PATCH và hệ thống phân tán.
- Khi thay đổi API, kiểm tra các điểm gọi và hành vi client trước khi loại bỏ quy ước cũ.

Mã nguồn dễ hiểu và đáng tin cậy bắt đầu từ một cam kết nhỏ: **người gọi biết chắc kiểu dữ liệu trả về có ý nghĩa gì và phải xử lý trường hợp vắng mặt ra sao**.

