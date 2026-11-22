# Khi deconstruction làm mất ngữ cảnh trong Java record patterns

## 1. Mô hình tư duy: dữ liệu có cấu trúc cũng có ý nghĩa

**Deconstruction** là việc phân rã một record thành các thành phần được khai báo trong record đó. Với Java 21+, record pattern cho phép phân rã ngay tại điểm kiểm tra cấu trúc, chẳng hạn trong `instanceof` hoặc `switch`.

Giả sử một đơn hàng có khách hàng và địa chỉ giao hàng; khách hàng lại có địa chỉ liên hệ:

```text
Order(orderId, customer, shippingAddress)
  ├── Customer(customerId, contactAddress)
  │     └── Address(city, country)     ← địa chỉ liên hệ
  └── Address(city, country)           ← địa chỉ giao hàng
```

Hai nút cuối đều thuộc kiểu `Address` nhưng **vai trò khác nhau**. Thành phố của địa chỉ liên hệ không nhất thiết là thành phố giao hàng; mã khách hàng không phải mã đơn hàng. Cấu trúc record cho chúng ta biết một dữ liệu thuộc **đối tượng nào**, dùng cho **việc gì**, và quan hệ giữa các phần.

Ta có thể lấy tất cả giá trị trong một biểu thức:

```java
if (source instanceof Order(
        var orderId,
        Customer(var customerId, Address(var contactCity, var contactCountry)),
        Address(var shippingCity, var shippingCountry))) {
    // Có sáu biến thành phần để xử lý.
}
```

Đây là cú pháp hợp lệ khi `Order`, `Customer`, `Address` là các record có số thành phần và thứ tự tương ứng. Nhưng sau khi chỉ sử dụng sáu biến riêng lẻ, người đọc phải tự nhớ rằng `contactCity` thuộc `customer.contactAddress()` và `shippingCity` thuộc `order.shippingAddress()`.

**“Mất ngữ cảnh” ở đây là nguy cơ trong thiết kế và cách đọc mã nguồn:** ta phân rã quá sớm/quá sâu rồi mang các giá trị rời rạc đi xử lý, khiến quan hệ cha–con, vai trò nghiệp vụ và nguồn gốc dữ liệu khó nhìn thấy. Bản thân Java **không xóa đối tượng gốc hay xóa metadata** khi thực hiện record pattern; nếu vẫn giữ một tham chiếu đến record, ta vẫn có thể dùng record đó. Vấn đề xảy ra khi phần mã tiếp theo không còn giữ hoặc không dùng những tham chiếu mang ngữ nghĩa ấy.

## 2. Cơ chế record pattern và giới hạn của nó

Ví dụ các record:

```java
record Address(String city, String country) {}
record Customer(String customerId, Address contactAddress) {}
record Order(String orderId, Customer customer, Address shippingAddress) {}
```

Mẫu `Order(var id, var customer, var destination)` kiểm tra đối tượng ngoài cùng là `Order` và ràng buộc các thành phần theo **đúng thứ tự khai báo**. Kiểu `customer` được suy ra là `Customer`, `destination` là `Address`. Mẫu chỉ mô tả cấu trúc và phép ràng buộc; nó **không hiểu** rằng “destination” phải là nơi giao hàng hoặc “contact” là địa chỉ liên hệ. Những ý nghĩa đó do tên thành phần, kiểu miền nghiệp vụ và phần xử lý của chương trình quy định.

Nếu đi sâu hơn:

```java
if (source instanceof Order(
        var id,
        Customer(var customerId, Address(var homeCity, var homeCountry)),
        Address(var deliveryCity, var deliveryCountry))) {
    // Có thể xử lý trực tiếp các thành phố và quốc gia.
}
```

Một số sự kiện quan trọng:

- Mẫu sâu chỉ khớp khi record ngoài cùng và các record lồng nhau được yêu cầu thực sự khớp; `Customer` hoặc `Address` bằng `null` thì mẫu record tương ứng không khớp.
- Thành phần dạng `var city` **vẫn có thể nhận `null`** nếu đối tượng `Address` tồn tại nhưng `city` bằng `null`. Record pattern không thay thế việc kiểm tra dữ liệu hợp lệ.
- Tên biến `homeCity`, `deliveryCity` do người viết lựa chọn; trình biên dịch lấy thành phần theo **vị trí**, không suy diễn nội dung từ tên biến.
- Các biến ràng buộc bởi pattern có phạm vi dùng được theo quy tắc kiểm soát luồng của Java. Không thể tùy ý dùng chúng ở mọi nhánh, đặc biệt sau một nhánh mà mẫu có thể thất bại.
- Khi đã bỏ các nút trung gian ra khỏi phần xử lý, ví dụ không ràng buộc một biến `Customer customer`, ta phải dựa vào tên biến hoặc giữ tham chiếu đầu vào nếu muốn khôi phục quan hệ giữa các giá trị.

Record patterns là tính năng chính thức từ **Java 21 (JEP 440)**. Chúng phù hợp để trích các thành phần cần thiết, không phải lý do để phân rã toàn bộ đồ thị đối tượng ở mọi nơi.

## 3. Năm tình huống dễ làm mất ngữ cảnh

### 3.1. Mất nguồn gốc: một giá trị không còn gắn với record đã sinh ra nó

Đoạn mã sau đặt tên khá rõ ràng, nhưng phương thức `sendReport` chỉ nhận các chuỗi riêng lẻ:

```java
// Minh họa ý tưởng: sendReport là hàm của ứng dụng.
if (source instanceof Order(var orderId,
        Customer(var customerId, var contactAddress),
        var shippingAddress)) {
    sendReport(orderId, customerId,
            contactAddress.city(), shippingAddress.city());
}
```

Khi đi qua ranh giới hàm, hai thành phố đều có kiểu `String`. Nếu bên nhận không còn đối tượng `Address` hoặc tên tham số đủ rõ, rất dễ hoán đổi nơi liên hệ với nơi giao hàng. Hơn nữa, mẫu trên chấp nhận `contactAddress == null` hoặc `shippingAddress == null`: lời gọi `.city()` có thể ném `NullPointerException`. Mẫu ngoài cùng khớp **không chứng minh** mọi record con khác `null`.

Phương án rõ hơn cho một nghiệp vụ cần biết vai trò của hai địa chỉ là truyền nguyên record với tên tham số có ý nghĩa, ví dụ `sendReport(Order order)` hoặc `sendReport(Address contactAddress, Address shippingAddress)`, sau đó kiểm tra dữ liệu cần dùng ở nơi phù hợp. Đây là quyết định thiết kế API; không phải Java tự ngăn việc truyền chuỗi.

### 3.2. Mất ranh giới nhóm: các giá trị thuộc cùng một khái niệm bị tách rời

Giả sử `Price(amount, currency)` biểu diễn giá tiền. Nếu phân rã hai `Price` (giá gốc và giá sau giảm) thành `originalAmount`, `originalCurrency`, `saleAmount`, `saleCurrency`, Java vẫn cho phép nhầm `saleAmount` với `originalCurrency` trong các phép xử lý chỉ dùng `BigDecimal` và `String`. Hai giá trị ghép nhầm vẫn có kiểu hợp lệ, nhưng sai về nghiệp vụ.

```java
// Giả sử Offer có hai thành phần Price: original, sale.
if (source instanceof Offer(
        Price(var originalAmount, var originalCurrency),
        Price(var saleAmount, var saleCurrency))) {
    // Cảnh báo: saleAmount đi với originalCurrency là một cặp sai vai trò.
    // Không phải lỗi kiểu nếu cả hai currency đều là String.
}
```

Nếu nghiệp vụ cần chuyển tiếp **một giá trọn vẹn**, nên giữ `Price` thành một giá trị thống nhất:

```java
if (source instanceof Offer(var originalPrice, var salePrice)) {
    // Ví dụ minh họa: truyền salePrice như một Price,
    // thay vì truyền riêng amount và currency.
}
```

Hai khối trên là **đoạn minh họa**, không phải chương trình độc lập: cần có khai báo `Price`, `Offer` và `source`. Ý chính là dữ liệu như số tiền và loại tiền nên đi cùng nhau qua ranh giới API, nhất là khi có quy tắc kiểm định/định dạng gắn với kiểu miền nghiệp vụ.

### 3.3. Mất sự phân biệt vai trò khi hai nhánh có hình dạng giống nhau

`contactAddress` và `shippingAddress` đều là `Address(String city, String country)`. Nếu viết:

```java
if (source instanceof Order(var id,
        Customer(var customerId, Address(var cityA, var countryA)),
        Address(var cityB, var countryB))) {
    System.out.println(cityA + " / " + cityB);
}
```

Ta buộc phải nhớ `A` là liên hệ, `B` là giao hàng. Vấn đề nghiêm trọng hơn khi đổi thứ tự thành phần trong một bản tái cấu trúc: các thành phần cùng kiểu có thể hoán đổi ý nghĩa mà mã vẫn biên dịch. Tên rõ vai trò (`contactCity`, `shippingCity`) giảm rủi ro, nhưng việc giữ nguyên `Address contactAddress` và `Address shippingAddress` còn giúp mối quan hệ hiển hiện khi đọc mã.

### 3.4. Mất khả năng phân biệt lý do không khớp

Một mẫu lồng sâu có thể không khớp bởi nhiều nguyên nhân: đầu vào không phải `Order`; đơn hàng thiếu khách hàng; khách hàng thiếu địa chỉ liên hệ; hoặc đơn hàng thiếu địa chỉ giao hàng. Nếu chỉ viết:

```java
if (source instanceof Order(
        var id,
        Customer(var customerId, Address(var contactCity, var contactCountry)),
        Address(var shipCity, var shipCountry))) {
    // Xử lý dữ liệu đầy đủ.
} else {
    // Tất cả nguyên nhân không khớp đều vào đây.
}
```

Nhánh `else` không cho biết record nào còn thiếu. Khi nghiệp vụ cần báo lỗi chính xác hoặc chấp nhận một phần dữ liệu, việc phân rã toàn bộ ngay lập tức có thể **che mất khả năng rẽ nhánh theo từng tầng**. Một giải pháp là kiểm tra `Order` trước, giữ `order`, rồi kiểm tra `customer`, `contactAddress` và `shippingAddress` riêng.

### 3.5. Mất thông tin miền nghiệp vụ khi đưa dữ liệu đi xa

Một record có thể là *đối tượng giá trị* (value object) chứa các quy tắc trong constructor và phương thức riêng: `Money` bảo đảm đơn vị tiền, `DateRange` bảo đảm điểm bắt đầu không sau điểm kết thúc, `Address` có thể cung cấp hàm định dạng. Sau deconstruction, dữ liệu rời như `amount`, `currency` hoặc `start`, `end` không tự mang theo API và ý nghĩa gắn với record gốc.

**Không phải quy tắc đã kiểm định bị xóa khỏi đối tượng**, mà là người nhận các giá trị rời có thể thiếu kiểu và API cần thiết để duy trì/áp dụng quy tắc ấy. Nếu một thao tác làm việc với cả khái niệm, hãy truyền record thay cho một tập tham số cùng kiểu khó phân biệt.

## 4. Ví dụ hoàn chỉnh: so sánh phân rã sâu và giữ ngữ cảnh

Lưu chương trình sau vào **`DeconstructionContextDemo.java`**. Mã và dữ liệu in ra dùng ký tự ASCII để kết quả hiển thị ổn định trên nhiều terminal; phần giải thích vẫn dùng tiếng Việt.

```java
public class DeconstructionContextDemo {
    record Address(String city, String country) {}
    record Customer(String customerId, Address contactAddress) {}
    record Order(String orderId, Customer customer, Address shippingAddress) {}

    // Lay het thanh phan sau ba tang trong mot mau.
    static String allAtOnce(Object source) {
        if (source instanceof Order(
                var id,
                Customer(var customerId, Address(var contactCity, var contactCountry)),
                Address(var shipCity, var shipCountry))) {
            return id + ": customer=" + customerId
                    + " contact=" + contactCity + "/" + contactCountry
                    + " ship=" + shipCity + "/" + shipCountry;
        }
        return "No complete structure";
    }

    // Giu Order, Customer va Address de biet ro quan he cha-con.
    static String preserveLinks(Object source) {
        if (!(source instanceof Order order)) {
            return "Not an order";
        }
        Customer customer = order.customer();
        Address destination = order.shippingAddress();
        if (customer == null) {
            return order.orderId() + ": missing customer";
        }
        if (destination == null) {
            return order.orderId() + ": missing shipping address";
        }
        Address contact = customer.contactAddress();
        if (contact == null) {
            return order.orderId() + ": missing contact address";
        }
        return order.orderId() + ": ship=" + destination.city()
                + " / contact=" + contact.city();
    }

    // Chi phan ra tang ngoai; hai record con van giu nguyen vai tro.
    static String selective(Object source) {
        if (source instanceof Order(var id, var customer, var destination)
                && customer != null && destination != null) {
            return id + ": customer=" + customer.customerId()
                    + ", ship=" + destination.city();
        }
        return "Insufficient data";
    }

    public static void main(String[] args) {
        Order full = new Order("O-101",
                new Customer("C-9", new Address("Ha Noi", "VN")),
                new Address("Da Nang", "VN"));
        Order missingContact = new Order("O-102",
                new Customer("C-9", null),
                new Address("Da Nang", "VN"));

        System.out.println(allAtOnce(full));
        System.out.println(preserveLinks(full));
        System.out.println(selective(full));

        System.out.println(allAtOnce(missingContact));
        System.out.println(preserveLinks(missingContact));
        System.out.println(selective(missingContact));

        System.out.println(preserveLinks("other"));
        System.out.println(selective(new Order("O-103", null,
                new Address("Hue", "VN"))));
    }
}
```

Biên dịch và chạy bằng JDK 21 trở lên:

```bash
javac --release 21 -encoding UTF-8 DeconstructionContextDemo.java
java DeconstructionContextDemo
```

Đầu ra chính xác:

```text
O-101: customer=C-9 contact=Ha Noi/VN ship=Da Nang/VN
O-101: ship=Da Nang / contact=Ha Noi
O-101: customer=C-9, ship=Da Nang
No complete structure
O-102: missing contact address
O-102: customer=C-9, ship=Da Nang
Not an order
Insufficient data
```

### Giải thích từng cách

**`allAtOnce`** tạo sáu biến ngay trong một mẫu. Rất ngắn nếu đúng nhu cầu là trình bày cả hai địa chỉ, nhưng khi địa chỉ liên hệ bằng `null` thì mẫu sâu thất bại; lời báo `No complete structure` không chỉ ra thiếu nút nào. Cũng không có biến `customer` hay `destination` được ràng buộc trực tiếp để xử lý tiếp với kiểu record, nên phần thân dễ chuyển sang chỉ làm việc với chuỗi.

**`preserveLinks`** chỉ kiểm tra `Order` ở bước đầu, rồi giữ các biến `Customer customer`, `Address destination`, `Address contact`. Điều này giúp đặt kiểm tra `null` vào đúng mắt xích và giải thích thiếu dữ liệu nào. Giá trị vẫn đi qua các accessor có tên vai trò: `order.shippingAddress()` và `customer.contactAddress()`.

**`selective`** phân rã `Order` một tầng, giữ nguyên hai record con. Khi chỉ cần mã khách hàng và địa chỉ giao hàng, nó vẫn có thể xử lý đơn `O-102` dù khách hàng chưa có địa chỉ liên hệ. Nhờ đó, phạm vi yêu cầu dữ liệu của phương thức rõ hơn: chỉ cần `customer` và `destination`, chưa cần `customer.contactAddress`.

Không có cách nào luôn tốt nhất: chọn mức phân rã theo **thao tác thực sự cần làm** và mức thông tin cần giữ lại. Các đối tượng không “biến mất” khỏi heap do `allAtOnce`; chỉ là ta không ràng buộc biến trung gian trong mẫu ấy.

## 5. Cách giữ ngữ cảnh khi vẫn muốn dùng pattern matching

### 5.1. Dừng đúng tầng cần thiết

Nếu chỉ cần địa chỉ giao hàng, không cần trích địa chỉ liên hệ:

```java
if (source instanceof Order(var orderId, var customer, var shippingAddress)
        && shippingAddress != null) {
    System.out.println(orderId + ": " + shippingAddress.city());
}
```

Đây là đoạn minh họa dựa trên các record ở mục 4. Nó giữ `Customer` như một nút riêng và không bắt buộc địa chỉ liên hệ phải tồn tại.

### 5.2. Đặt tên theo vai trò, không đặt theo kiểu chung chung

Hai tên `city1` và `city2` có cùng kiểu nên thiếu thông tin về nơi sử dụng. `contactCity`, `shippingCity` nói lên nhiều hơn. Tương tự, với `Price` nên dùng `originalPrice` và `salePrice`; với `DateRange` dùng `startDate` và `endDate` thay vì `first` và `second`.

Tên biến rõ ràng là một lớp bảo vệ, nhưng khi nhiều trường cùng kiểu được truyền qua hàm hoặc lớp khác, **kiểu miền nghiệp vụ** thường đáng tin hơn một danh sách tham số nguyên thủy.

### 5.3. Giữ record cha hoặc record con trong những nhánh còn cần nó

```java
if (source instanceof Order order) {
    Customer customer = order.customer();
    Address destination = order.shippingAddress();

    if (customer != null && destination != null) {
        // Co ca Order, Customer va Address de xu ly tiep.
    }
}
```

Với cách này, `order.orderId()`, `customer.customerId()` và `destination.country()` luôn cho thấy mối liên hệ giữa dữ liệu và đối tượng. Ta cũng có thể trích một tầng bằng `Order(var id, var customer, var destination)` nếu thích cú pháp record pattern.

Java 21 không cung cấp một cú pháp `as` chung để **vừa ràng buộc chính record ở nút đó, vừa phân rã tất cả thành phần trong cùng một record pattern**. Vì vậy, khi cần giữ cả record cha cho nhiều thao tác, khai báo một biến record qua mẫu kiểu (`source instanceof Order order`) là cách dễ đọc.

### 5.4. Kiểm tra điều kiện nghiệp vụ sau bước phân rã

Một mẫu khớp không chứng minh chuỗi có nội dung, quốc gia thuộc danh sách cho phép hay địa chỉ đủ để giao hàng. Ví dụ:

```java
if (source instanceof Order(
        var id, var customer, Address(var city, var country))
        && city != null && !city.isBlank()
        && "VN".equals(country)) {
    System.out.println("Ship to " + city + " for order " + id);
}
```

Ở đây `Address(...)` đòi hỏi địa chỉ giao hàng là một record phù hợp; phần điều kiện sau `&&` kiểm tra dữ liệu phục vụ nghiệp vụ. Nếu chỉ có một địa chỉ dùng cho hiển thị, có thể giữ nguyên `Address shippingAddress` rồi gọi một hàm kiểm tra hoặc định dạng trên kiểu đó.

### 5.5. Giữ các nhóm giá trị đi cùng nhau qua ranh giới phương thức

Nên cân nhắc phương thức nhận `Price` hoặc `Address` nếu phần xử lý cần cả khái niệm, nhất là khi cần kiểm tra tính hợp lệ và truyền tiếp nhiều lớp. Việc truyền từng trường `String city`, `String country`, `BigDecimal amount`, `String currency` phù hợp hơn khi API thật sự chỉ dùng từng trường và tên tham số đã rõ.

Nên chọn mức tối thiểu mang **đủ ý nghĩa**; không cần chuyển cả `Order` vào một hàm chỉ định dạng `Address`. Giữ đúng record nhỏ nhất chứa các dữ liệu liên quan là một điểm cân bằng hữu ích.

## 6. Bảng quyết định: nên phân rã sâu đến đâu?

| Bài toán | Cách tiếp cận | Nguyên nhân |
| --- | --- | --- |
| In đúng một trường sâu và dữ liệu bắt buộc đầy đủ | Mẫu record lồng nhau | Diễn đạt gọn cấu trúc cần thiết |
| Xử lý đồng thời địa chỉ liên hệ và giao hàng | Giữ hai biến `Address` theo vai trò hoặc đặt tên biến rất rõ | Tránh nhầm hai nhánh cùng kiểu |
| Cần báo nguyên nhân thiếu dữ liệu cụ thể | Kiểm tra từng tầng, giữ biến record trung gian | Phân biệt `Customer` thiếu với `Address` thiếu |
| Cần truyền một giá tiền sang nhiều tầng xử lý | Giữ `Price/Money` như đối tượng giá trị | Bảo toàn nhóm amount/currency và API đi kèm |
| Chỉ cần mã đơn hàng và địa chỉ giao hàng | Phân rã `Order` một tầng, giữ `Address` | Không buộc địa chỉ liên hệ phải tồn tại |
| Đồ thị sâu, nhiều nhánh tùy chọn hoặc quy tắc thay đổi | Chia thành những bước/ phương thức có tên rõ | Dễ kiểm tra điều kiện và bảo trì hơn |

Một dấu hiệu đơn giản: nếu một mẫu có nhiều biến cùng kiểu (`id1`/`id2`, `cityA`/`cityB`, `amount1`/`amount2`) và phần thân lại truyền chúng qua nhiều hàm, hãy tự hỏi liệu các record gốc có truyền đạt ý nghĩa tốt hơn không.

## 7. Những hiểu lầm và lỗi thường gặp

1. **“Deconstruction làm biến mất đối tượng.”** Sai. Record pattern so khớp cấu trúc và ràng buộc thành phần; nó không xóa đối tượng. Mất ngữ cảnh xảy ra khi phần xử lý chỉ dùng các thành phần rời và bỏ quan hệ ở cấp thiết kế mã.
2. **“Phân rã sâu luôn tốt vì ít dòng hơn.”** Sai. Mẫu ngắn có thể làm các điều kiện dữ liệu bắt buộc trở nên quá chặt hoặc khiến một nhánh `else` gom nhiều nguyên nhân thất bại khác nhau.
3. **“Hai record cùng kiểu có thể hoán đổi an toàn.”** Sai về nghiệp vụ dù trình biên dịch có thể không phát hiện. `contactAddress` và `shippingAddress` cùng kiểu `Address` nhưng vai trò khác nhau.
4. **“Record pattern xác minh giá trị hợp lệ.”** Không. Nó không kiểm tra sẵn chuỗi rỗng, quy tắc quốc gia, quan hệ giữa số tiền và loại tiền hoặc ràng buộc nghiệp vụ tùy chỉnh.
5. **“Mẫu `var` luôn khác `null` khi khớp.”** Không. Nếu record tồn tại, thành phần kiểu tham chiếu có thể là `null`; trong khi bản thân một record con bằng `null` không khớp mẫu record lồng nhau.
6. **“Dùng mẫu sâu thì không cần kiểm tra trường con.”** Không. Nếu chọn mẫu `Order(var id, var customer, var destination)`, `customer` và `destination` vẫn có thể bằng `null`. Gọi accessor cần được bảo vệ theo đúng dữ liệu đầu vào.
7. **“Các tên biến quyết định vị trí thành phần.”** Không. Thứ tự trong `RecordName(...)` phải theo thứ tự thành phần record. Cẩn thận khi có nhiều thành phần cùng kiểu: đổi tên biến không làm Java tự hoán đổi đúng vai trò.
8. **“Muốn giữ record cha thì bắt buộc bỏ pattern matching.”** Không. Có thể dùng `instanceof Order order` để giữ bản thân record, hoặc dùng `Order(var id, var customer, var destination)` để giữ các record con thay vì đi sâu ngay.

## 8. Bài tập tự kiểm tra

**Bài 1 — Đọc cấu trúc.** Với `Order("O-102", Customer("C-9", null), Address("Da Nang", "VN"))`, tại sao mẫu `Order(var id, Customer(var cid, Address(var city, var country)), var destination)` không khớp? **Đáp án:** `contactAddress` của `Customer` bằng `null` nên không khớp `Address(...)`, dù `shippingAddress` tồn tại.

**Bài 2 — Chọn tầng phân rã.** Một chức năng chỉ cần `orderId` và `shippingAddress.country()` để chọn vùng vận chuyển. Có nên phân rã cả `Customer.contactAddress` không? **Đáp án:** không cần; kiểm tra `Order` và địa chỉ giao hàng là đủ. Yêu cầu thêm địa chỉ liên hệ sẽ loại những đơn hàng mà chức năng vốn xử lý được.

**Bài 3 — Phát hiện nhầm vai trò.** Nhận `contactCity` và `shippingCity` đều là `String`. Một hàm kiểm tra phí vận chuyển lại dùng `contactCity`. Trình biên dịch có nhất thiết báo lỗi? **Đáp án:** không. Lỗi nằm ở ý nghĩa nghiệp vụ; giữ hoặc truyền tham số có tên `shippingAddress` giúp dễ phát hiện hơn.

**Bài 4 — Giữ nhóm dữ liệu.** Với `record Price(BigDecimal amount, String currency)`, lựa chọn nào tốt hơn nếu hàm cần tính toán và hiển thị một giá đầy đủ: truyền cả `Price` hay truyền hai tham số rời? **Đáp án gợi ý:** truyền `Price` khi cần giữ quan hệ amount/currency, kiểm định và API của giá; truyền các trường riêng nếu API chỉ thực sự cần từng giá trị và hợp đồng hàm đã rõ.

**Bài 5 — Phân biệt dữ liệu thiếu.** Trong chương trình mục 4, vì sao `selective(missingContact)` vẫn cho kết quả hợp lệ trong khi `allAtOnce(missingContact)` không? **Đáp án:** `selective` không yêu cầu `Customer.contactAddress` tồn tại; `allAtOnce` yêu cầu một `Address` lồng trong `Customer` để phân rã.

## 9. Ghi nhớ

Deconstruction giúp **diễn đạt rõ hình dạng cần so khớp** và lấy dữ liệu ngay tại vị trí sử dụng. Nó bắt đầu làm **mất ngữ cảnh trong cách thiết kế mã** khi ta phân rã quá sâu hoặc quá sớm, chỉ giữ các giá trị cùng kiểu mà bỏ mất quan hệ cha–con, vai trò và nhóm dữ liệu nghiệp vụ. Hãy phân rã đến mức đủ cho thao tác, đặt tên thể hiện nguồn gốc, giữ record trung gian khi cần, kiểm tra `null` đúng tầng và truyền nguyên đối tượng giá trị qua ranh giới API khi mối liên hệ giữa các thành phần quan trọng.

**Tài liệu tham khảo:** [JEP 440 — Record Patterns](https://openjdk.org/jeps/440), [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html), [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441).
