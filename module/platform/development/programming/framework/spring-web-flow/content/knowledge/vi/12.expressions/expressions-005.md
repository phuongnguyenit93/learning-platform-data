# Đọc thuộc tính, collection và giá trị lồng nhau trong biểu thức Spring Web Flow

Trong một flow đặt hàng, dữ liệu thường không nằm trong một biến đơn. Bản nháp có khách hàng, địa chỉ, danh sách sản phẩm, tùy chọn giao hàng và metadata. Một biểu thức điều hướng có thể cần đọc thành phố của khách hàng; một action có thể tính tổng số lượng sản phẩm; một view có thể hiển thị tên mặt hàng đầu tiên. Nếu không hiểu cách truy cập **thuộc tính lồng nhau**, **collection** và **giá trị trong map**, biểu thức trong flow dễ gặp lỗi null, sai chỉ số hoặc vô tình gọi những phép xử lý tốn kém.

Spring Web Flow (SWF) dùng expression language để đọc và cập nhật dữ liệu trong ngữ cảnh flow. Các ví dụ trong bài sử dụng cú pháp **Spring Expression Language (SpEL)** phổ biến với cấu hình SWF tương ứng. Cú pháp cụ thể phụ thuộc expression parser được khai báo trong `flow-builder-services`; nếu ứng dụng chọn Unified EL hoặc parser khác, cần đối chiếu cú pháp của parser đang dùng.

Bài thuộc chương **Biểu thức** của module `SPRING_WEB_FLOW`. Nội dung đi từ JavaBean property path, object lồng nhau, list/array/map, collection selection/projection, xử lý null và chỉ số, đến cách đưa expression vào flow XML, kiểm thử, bảo mật và tối ưu hiệu năng.

## 1. Ngữ cảnh expression và các scope

Một biểu thức trong flow không chạy trong khoảng trống. SWF cung cấp evaluation context với những đối tượng đặc biệt như `flowScope`, `viewScope`, `requestScope`, `conversationScope`, `flashScope`, `requestParameters` và thông tin event hiện tại. Chúng cho phép biểu thức truy cập dữ liệu theo đúng phạm vi của flow.

Ví dụ, nếu flow đã khởi tạo `orderDraft`:

~~~xml
<var name="orderDraft" class="com.example.checkout.OrderDraft" />

<decision-state id="checkOrder">
    <if test="flowScope.orderDraft != null"
        then="reviewOrder"
        else="restartRequired" />
</decision-state>
~~~

`flowScope.orderDraft` là đối tượng bản nháp được giữ trong flow session. Từ đó, SpEL có thể đi sâu vào các thuộc tính của object:

~~~xml
<if test="flowScope.orderDraft.customer.email != null"
    then="checkAddress"
    else="enterContact" />
~~~

Đọc theo chuỗi: lấy `orderDraft` trong `flowScope`, lấy thuộc tính `customer`, rồi đọc `email` của customer. Mỗi dấu chấm biểu thị một lần truy cập thuộc tính trên object trước đó.

| Nguồn expression | Mục đích | Ví dụ |
|---|---|---|
| `flowScope` | Dữ liệu cần giữ qua nhiều state của flow session | `flowScope.orderDraft` |
| `viewScope` | Dữ liệu thuộc view-state hiện tại | `viewScope.searchFilter` |
| `requestScope` | Dữ liệu tạm của request đang xử lý | `requestScope.notice` |
| `conversationScope` | Dữ liệu chia sẻ có chủ đích trong conversation | `conversationScope.locale` |
| `flashScope` | Thông báo ngắn hạn qua bước render tiếp theo | `flashScope.message` |
| `requestParameters` | Giá trị request do client gửi | `requestParameters.page` |
| `currentEvent` | Event đang được xử lý trong context thích hợp | `currentEvent.id` |

Không phải expression nào cũng cần truy cập scope. Khi dùng scope, nên ghi rõ tiền tố để người đọc hiểu dữ liệu đến từ đâu và tồn tại trong bao lâu. Đặc biệt, `requestParameters` là dữ liệu đầu vào không đáng tin cậy; không dùng trực tiếp để cấp quyền, tính giá hoặc xác nhận trạng thái thanh toán.

## 2. Đọc thuộc tính JavaBean bằng dấu chấm

SpEL hỗ trợ truy cập thuộc tính theo **property path**. Với JavaBean thông thường, property `email` được đọc qua getter `getEmail()`; property boolean có thể dùng getter `isActive()` theo quy ước JavaBean.

Giả sử có mô hình:

~~~java
package com.example.checkout;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class OrderDraft {
    private Customer customer;
    private List<OrderLine> items = new ArrayList<>();
    private Map<String, String> attributes = new HashMap<>();
    private BigDecimal shippingFee = BigDecimal.ZERO;

    public Customer getCustomer() { return customer; }
    public void setCustomer(Customer customer) { this.customer = customer; }

    public List<OrderLine> getItems() { return items; }
    public void setItems(List<OrderLine> items) { this.items = items; }

    public Map<String, String> getAttributes() { return attributes; }
    public void setAttributes(Map<String, String> attributes) {
        this.attributes = attributes;
    }

    public BigDecimal getShippingFee() { return shippingFee; }
    public void setShippingFee(BigDecimal shippingFee) {
        this.shippingFee = shippingFee;
    }
}

class Customer {
    private Address address;
    private String email;

    public Address getAddress() { return address; }
    public void setAddress(Address address) { this.address = address; }

    public String getEmail() { return email; }
    public void setEmail(String email) { this.email = email; }
}

class Address {
    private String city;
    private String postalCode;

    public String getCity() { return city; }
    public void setCity(String city) { this.city = city; }

    public String getPostalCode() { return postalCode; }
    public void setPostalCode(String postalCode) {
        this.postalCode = postalCode;
    }
}

class OrderLine {
    private Product product;
    private int quantity;
    private BigDecimal unitPrice;

    public Product getProduct() { return product; }
    public void setProduct(Product product) { this.product = product; }

    public int getQuantity() { return quantity; }
    public void setQuantity(int quantity) { this.quantity = quantity; }

    public BigDecimal getUnitPrice() { return unitPrice; }
    public void setUnitPrice(BigDecimal unitPrice) {
        this.unitPrice = unitPrice;
    }
}

class Product {
    private String name;
    private String sku;

    public String getName() { return name; }
    public void setName(String name) { this.name = name; }

    public String getSku() { return sku; }
    public void setSku(String sku) { this.sku = sku; }
}
~~~

Các class lồng trong ví dụ được viết rút gọn để làm rõ property; trong dự án thực, mỗi kiểu có thể nằm ở file riêng và cần constructor, validation, visibility phù hợp.

Một số expression đọc object graph:

~~~xml
<!-- Đọc email khách hàng -->
<evaluate expression="flowScope.orderDraft.customer.email"
          result="flowScope.customerEmail" />

<!-- Đọc thành phố giao hàng -->
<if test="flowScope.orderDraft.customer.address.city == 'Ho Chi Minh City'"
    then="localDelivery"
    else="standardDelivery" />

<!-- Đọc phí giao hàng -->
<evaluate expression="flowScope.orderDraft.shippingFee"
          result="flowScope.currentShippingFee" />
~~~

`result` trong ví dụ lưu giá trị expression vào một scope khác. Phải bảo đảm các object trung gian (`orderDraft`, `customer`, `address`) đã được khởi tạo trước khi truy cập sâu.

### 2.1. Property path không phải tên field tùy ý

Expression property access thông thường đi qua cơ chế property accessor của parser, thường dựa trên JavaBean getter/setter. Vì vậy:

- `customer.email` thường tương ứng với `getCustomer().getEmail()`.
- `items` tương ứng với `getItems()`.
- `active` có thể tương ứng với `isActive()`.

Nếu tên property sai, getter không tồn tại hoặc accessor không hỗ trợ kiểu object, expression có thể phát sinh lỗi khi được đánh giá. Không nên đoán tên property từ tên cột database; hãy đối chiếu với API model thực tế.

### 2.2. Đọc property lồng nhiều cấp

Ví dụ:

~~~xml
<if test="flowScope.orderDraft.customer.address.postalCode != null"
    then="review"
    else="completeAddress" />
~~~

Expression có thể đọc sâu qua nhiều object, nhưng mỗi cấp là một điểm có thể null. Nếu `customer` hoặc `address` chưa tồn tại, việc truy cập tiếp có thể lỗi. Cách viết sâu gọn không làm mất yêu cầu kiểm tra tiền điều kiện.

## 3. Truy cập phần tử của list, array và map

SpEL dùng **indexer** trong dấu ngoặc vuông. Ý nghĩa của index phụ thuộc kiểu collection.

### 3.1. List và array

Với `List`, chỉ số bắt đầu từ `0`. Ví dụ:

~~~xml
<!-- Số lượng của phần tử đầu tiên -->
<evaluate expression="flowScope.orderDraft.items[0].quantity"
          result="flowScope.firstItemQuantity" />

<!-- Tên sản phẩm đầu tiên -->
<evaluate expression="flowScope.orderDraft.items[0].product.name"
          result="flowScope.firstProductName" />
~~~

Với array, cú pháp index tương tự:

~~~text
flowScope.orderDraft.tags[0]
flowScope.orderDraft.tags[1]
~~~

Trước khi truy cập `items[0]`, cần chắc chắn danh sách không null và có ít nhất một phần tử. Nếu danh sách rỗng, expression có thể phát sinh lỗi index; nếu phần tử đầu tiên null, việc đọc `.quantity` tiếp theo cũng có thể lỗi.

Một guard rõ ràng:

~~~xml
<decision-state id="checkItems">
    <if test="flowScope.orderDraft.items != null and
              !flowScope.orderDraft.items.isEmpty()"
        then="reviewFirstItem"
        else="emptyCart" />
</decision-state>
~~~

`and` trong SpEL đánh giá ngắn mạch, nên vế `isEmpty()` chỉ được gọi khi `items` khác null. Sau khi vào `reviewFirstItem`, flow có thể đọc phần tử `[0]` theo tiền điều kiện vừa kiểm tra; nếu có action khác có thể sửa danh sách giữa hai bước, vẫn phải kiểm tra lại ở nơi sử dụng.

### 3.2. Map

Với `Map`, biểu thức trong ngoặc vuông là **key**:

~~~xml
<!-- Map attributes có key channel -->
<if test="flowScope.orderDraft.attributes['channel'] == 'WEB'"
    then="webCheckout"
    else="otherCheckout" />

<!-- Đọc mã chiến dịch -->
<evaluate expression="flowScope.orderDraft.attributes['campaign-code']"
          result="flowScope.campaignCode" />
~~~

Cách dùng bracket notation đặc biệt hữu ích khi key chứa dấu gạch ngang, khoảng trắng hoặc ký tự không phù hợp với property path dạng dấu chấm. Với key thông thường, `attributes.channel` có thể được parser hiểu như property access của map tùy accessor; `attributes['channel']` diễn đạt rõ rằng đây là key.

Nếu key không tồn tại, giá trị trả về thường là null. Khi dùng kết quả, hãy kiểm tra null trước khi gọi method hoặc đọc property tiếp theo.

### 3.3. So sánh ba kiểu truy cập

| Cấu trúc Java | Cú pháp SpEL | Ý nghĩa |
|---|---|---|
| `customer.getEmail()` | `customer.email` | Đọc property |
| `items.get(0)` | `items[0]` | Đọc phần tử đầu list |
| `tags[1]` (array) | `tags[1]` | Đọc phần tử thứ hai |
| `attributes.get("channel")` | `attributes['channel']` | Đọc value theo map key |

Với `Set`, không nên dùng index như thể thứ tự phần tử ổn định. Nếu cần lấy phần tử theo vị trí, dùng `List` hoặc chuyển dữ liệu sang một cấu trúc có thứ tự rõ ràng.

## 4. Lọc và biến đổi collection bằng SpEL

Khi expression parser dùng SpEL và phiên bản hỗ trợ collection operators, có thể **selection** (lọc phần tử) và **projection** (biến đổi mỗi phần tử).

Giả sử `orderDraft.items` là list các `OrderLine`.

### 4.1. Selection: lấy những phần tử thỏa điều kiện

Toán tử `.?[ ... ]` lọc collection theo predicate:

~~~xml
<!-- Các dòng có số lượng dương -->
<evaluate expression="flowScope.orderDraft.items.?[quantity gt 0]"
          result="flowScope.validItems" />

<!-- Các dòng có giá trị đơn vị lớn hơn 500000 -->
<evaluate expression="flowScope.orderDraft.items.?[unitPrice gt 500000]"
          result="flowScope.highValueItems" />
~~~

Trong predicate, property như `quantity` hoặc `unitPrice` được đánh giá trên từng phần tử hiện tại. Có thể viết tường minh bằng `#this`:

~~~text
flowScope.orderDraft.items.?[#this.quantity gt 0]
~~~

`#this` đại diện cho phần tử đang được xét. Selection trên một collection thường tạo collection kết quả chứa các phần tử thỏa điều kiện; không sửa collection nguồn.

### 4.2. Projection: lấy một thuộc tính từ từng phần tử

Toán tử `.![ ... ]` (cú pháp thực tế viết liền, không có khoảng trắng: `.![expression]`) tạo collection mới từ kết quả biểu thức trên từng phần tử:

~~~xml
<evaluate expression="flowScope.orderDraft.items.![product.name]"
          result="flowScope.productNames" />
~~~

Nếu list có ba dòng hàng, `productNames` là list tên sản phẩm tương ứng. Projection hữu ích khi view chỉ cần một thuộc tính đơn giản, không cần toàn bộ object.

### 4.3. Lấy phần tử đầu hoặc cuối khớp điều kiện

SpEL còn có selection operators:

| Toán tử | Ý nghĩa | Ví dụ |
|---|---|---|
| `.?[predicate]` | Tất cả phần tử thỏa điều kiện | `items.?[quantity gt 0]` |
| `.^[predicate]` | Phần tử đầu tiên thỏa điều kiện | `items.^[quantity gt 0]` |
| `.$[predicate]` | Phần tử cuối cùng thỏa điều kiện | `items.$[quantity gt 0]` |
| `.![expression]` | Projection; tạo giá trị từ mỗi phần tử | `items.![product.name]` |

Các toán tử selection/projection là tính năng của SpEL, không phải cú pháp chung của mọi expression language. Nếu dự án dùng Unified EL hoặc parser tùy chỉnh, không giả định những toán tử này tồn tại. Với collection rất lớn, cũng không nên lọc toàn bộ trong expression khi truy vấn database có thể thực hiện hiệu quả hơn.

### 4.4. Kết hợp collection với điều kiện trong flow

Ví dụ chỉ cho phép review khi có ít nhất một dòng hàng hợp lệ:

~~~xml
<decision-state id="checkCart">
    <if test="flowScope.orderDraft.items != null and
              !flowScope.orderDraft.items.?[quantity gt 0].isEmpty()"
        then="reviewOrder"
        else="emptyCart" />
</decision-state>
~~~

Trong một flow quan trọng, biểu thức dài như trên có thể khó đọc và phụ thuộc vào kiểu collection trả về. Một cách rõ hơn là dùng method chỉ đọc hoặc action Java để tính flag:

~~~xml
<decision-state id="routeCart">
    <if test="cartPolicy.hasPurchasableItems(flowScope.orderDraft)"
        then="reviewOrder"
        else="emptyCart" />
</decision-state>
~~~

`cartPolicy.hasPurchasableItems(...)` nên là phép kiểm tra nhanh, không có side effect. Nếu cần gọi database hoặc tính toán phức tạp, đặt nó trong action/service phù hợp thay vì khiến expression bị đánh giá lặp ngoài ý muốn.

## 5. Truy cập an toàn khi có giá trị null

Dữ liệu lồng nhau thường chưa đầy đủ. Một `OrderDraft` có thể tồn tại nhưng `customer` chưa được nhập; `customer` có thể có nhưng `address` chưa được tạo. Expression sau có thể lỗi:

~~~xml
<if test="flowScope.orderDraft.customer.address.city == 'Da Nang'"
    then="localDelivery"
    else="standardDelivery" />
~~~

### 5.1. Guard bằng điều kiện ngắn mạch

Cách tương thích rộng và dễ đọc là kiểm tra từng cấp trước:

~~~xml
<if test="flowScope.orderDraft != null and
          flowScope.orderDraft.customer != null and
          flowScope.orderDraft.customer.address != null and
          flowScope.orderDraft.customer.address.city == 'Da Nang'"
    then="localDelivery"
    else="completeAddress" />
~~~

Vì `and` đánh giá ngắn mạch, các vế sau chỉ được kiểm tra khi các vế trước đúng. Tuy nhiên, nếu `city` có thể null thì so sánh bằng chuỗi vẫn cho kết quả false; nếu cần phân biệt thiếu thành phố với thành phố khác, tạo nhánh kiểm tra riêng.

### 5.2. Safe navigation trong SpEL

SpEL hỗ trợ toán tử safe navigation `?.` trong các phiên bản Spring phù hợp:

~~~text
flowScope.orderDraft.customer?.address?.city
~~~

Khi object ở ngay trước `?.` là null, biểu thức trả null thay vì ném lỗi tại bước truy cập đó. Nên đặt `?.` ở **mỗi mắt xích có thể null**. Ví dụ `customer?.address?.city` bảo vệ cả customer lẫn address; `customer.address?.city` vẫn có thể lỗi nếu customer null.

Safe navigation không biến một dữ liệu thiếu thành giá trị hợp lệ. Nếu biểu thức trả null, cần quyết định null có ý nghĩa gì ở nhánh tiếp theo. Với flow chạy trên phiên bản parser cũ hoặc parser không phải SpEL, kiểm tra cú pháp được hỗ trợ; nếu chưa chắc, dùng guard tường minh.

### 5.3. Null khác collection rỗng

| Giá trị | Ý nghĩa | Kiểm tra phù hợp |
|---|---|---|
| `items == null` | Chưa khởi tạo hoặc không có nguồn dữ liệu | `items != null` |
| `items.isEmpty()` | Collection tồn tại nhưng không có phần tử | `!items.isEmpty()` |
| `items[0] == null` | Có phần tử đầu nhưng giá trị phần tử là null | Kiểm tra phần tử trước khi đọc property |
| `attributes['channel'] == null` | Key không tồn tại hoặc value null | Kiểm tra key/value theo hợp đồng dữ liệu |

Đừng dùng một biểu thức duy nhất để gộp tất cả tình huống nếu hành vi nghiệp vụ khác nhau. Ví dụ giỏ hàng chưa tải dữ liệu có thể cần hiển thị lỗi hệ thống; giỏ hàng rỗng có thể hiển thị lời mời thêm sản phẩm.

## 6. Gán giá trị lồng nhau và chuyển đổi kiểu

Expression không chỉ đọc dữ liệu. SWF có thể dùng `<set>` hoặc thuộc tính `result` của `<evaluate>` để ghi giá trị vào scope:

~~~xml
<!-- Ghi metadata vào map của bản nháp -->
<set name="flowScope.orderDraft.attributes['source']"
     value="'web-flow'" />

<!-- Tính số dòng hàng và lưu kết quả -->
<evaluate expression="flowScope.orderDraft.items.size()"
          result="flowScope.itemCount" />
~~~

`<set>` cần được đặt trong vị trí hợp lệ của flow definition (ví dụ action hook hoặc transition theo schema). Value `'web-flow'` là literal string trong SpEL; dấu nháy đơn bên trong attribute XML giúp phân biệt literal với property reference.

Khi ghi vào property lồng nhau, các object trung gian phải tồn tại và property cần có setter hoặc cơ chế ghi mà parser hỗ trợ. Ví dụ gán `orderDraft.customer.address.city` sẽ không tự tạo `customer` và `address` nếu chúng đang null. Hãy khởi tạo model ở đầu flow hoặc dùng service/action tạo cấu trúc trước.

### 6.1. Chuyển đổi kiểu không thay thế validation

Khi binding request vào model, Spring Web Flow/Spring binding infrastructure có thể chuyển chuỗi thành kiểu đích (ví dụ `String` sang `Integer`, `LocalDate` hoặc `BigDecimal`) tùy conversion service/property editor đã cấu hình.

Expression đọc property thường nhận **giá trị đã có kiểu**. Không nên dựa vào implicit conversion để hợp thức hóa dữ liệu đầu vào. Với số tiền, ngày tháng và số lượng, hãy dùng kiểu phù hợp, cấu hình conversion rõ ràng, rồi validate miền giá trị.

Ví dụ kiểm tra số lượng:

~~~xml
<if test="flowScope.orderDraft.items[0].quantity gt 0"
    then="reviewOrder"
    else="correctQuantity" />
~~~

Điều kiện này giả định `items` tồn tại, có phần tử đầu và quantity đã được chuyển đổi thành kiểu số. Nếu request gửi chuỗi không thể chuyển đổi, đó là lỗi binding/conversion trước hoặc trong quá trình cập nhật model; không nên xem nó như điều kiện Boolean false.

## 7. Đặt expression trong flow XML một cách dễ đọc

Một flow definition tốt giúp người đọc thấy rõ dữ liệu nào được lấy, điều kiện nào được kiểm tra và kết quả được lưu ở đâu.

~~~xml
<flow xmlns="http://www.springframework.org/schema/webflow"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:schemaLocation="
        http://www.springframework.org/schema/webflow
        http://www.springframework.org/schema/webflow/spring-webflow-2.0.xsd">

    <var name="orderDraft" class="com.example.checkout.OrderDraft" />

    <decision-state id="hasCustomer">
        <if test="flowScope.orderDraft.customer != null"
            then="checkAddress"
            else="enterContact" />
    </decision-state>

    <decision-state id="checkAddress">
        <if test="flowScope.orderDraft.customer.address != null and
                  flowScope.orderDraft.customer.address.city != null"
            then="checkItems"
            else="enterAddress" />
    </decision-state>

    <decision-state id="checkItems">
        <if test="flowScope.orderDraft.items != null and
                  !flowScope.orderDraft.items.isEmpty()"
            then="reviewOrder"
            else="emptyCart" />
    </decision-state>

    <view-state id="enterContact" view="checkout/contact" />
    <view-state id="enterAddress" view="checkout/address" />
    <view-state id="reviewOrder" view="checkout/review" />
    <view-state id="emptyCart" view="checkout/empty-cart" />
</flow>
~~~

Ví dụ trên minh họa các property path và guard trong một flow; để chạy hoàn chỉnh, cần bổ sung event/transition cho các view-state và khởi tạo các object phù hợp trước khi đi vào decision-state.

### 7.1. XML escaping trong thuộc tính expression

Vì expression nằm trong XML attribute, phải tuân theo cú pháp XML:

| Ý định | Cách viết trong XML |
|---|---|
| So sánh nhỏ hơn | `&lt;` |
| So sánh nhỏ hơn hoặc bằng | `&lt;=` |
| Kết hợp AND | Dùng `and` hoặc escape `&&` thành `&amp;&amp;` |
| Literal string | Dùng dấu nháy đơn bên trong attribute nháy kép |
| Key map có dấu gạch ngang | `attributes['campaign-code']` |

Ví dụ:

~~~xml
<if test="flowScope.orderDraft.items.size() &lt; 1"
    then="emptyCart"
    else="reviewOrder" />
~~~

`>` thường có thể xuất hiện trực tiếp trong XML attribute, nhưng dùng toán tử SpEL dạng từ như `gt`/`ge` hoặc escape ký tự khi cần giúp biểu thức dễ đọc và tránh lỗi cú pháp.

### 7.2. Đừng đặt một biểu thức quá dài trong flow

Nếu một điều kiện vừa kiểm tra nhiều property, gọi ba service, lọc collection và tính toán tổng tiền, nó khó kiểm thử và khó biết lỗi đến từ đâu. Hãy tách thành:

- một Java method chỉ đọc, có tên diễn đạt nghiệp vụ;
- một action-state để thực hiện tính toán và lưu kết quả;
- một hoặc nhiều decision-state ngắn để điều hướng.

Expression nên mô tả **điều kiện hoặc phép truy xuất nhỏ**, không thay thế service layer.

## 8. Lỗi thường gặp khi đọc object graph và collection

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Lỗi property không tồn tại | Sai tên property, getter/accessor không có | Đối chiếu JavaBean và expression parser |
| Null pointer/property access exception | Một object trung gian null | Guard từng cấp hoặc dùng safe navigation nếu parser hỗ trợ |
| Index out of bounds | List/array rỗng hoặc index vượt kích thước | Kiểm tra size trước khi index |
| Kết quả map là null | Key không tồn tại hoặc value null | Kiểm tra key và hợp đồng dữ liệu |
| Không lọc được collection | Dùng selection syntax với parser không hỗ trợ SpEL | Xác nhận expression parser và phiên bản |
| `quantity gt 0` không chạy | Phần tử collection không có property hoặc kiểu không so sánh được | Kiểm tra model và dữ liệu |
| Projection trả danh sách null | Property được project có thể null | Kiểm tra từng phần tử và xử lý giá trị thiếu |
| Gán nested property thất bại | Object trung gian null hoặc không có setter | Khởi tạo object trước và kiểm tra property write access |
| Expression gọi database quá nhiều | Getter/service kích hoạt truy vấn hoặc lazy loading | Đưa dữ liệu cần thiết vào DTO, tính một lần trong action |
| Biểu thức XML không parse | Quên escape `<` hoặc `&` | Dùng `&lt;`, `&amp;` hoặc toán tử SpEL dạng từ |
| Kết quả khác dự kiến giữa môi trường | Parser/version khác nhau | Kiểm tra `flow-builder-services` và dependencies |

### 8.1. Lazy loading và biểu thức có chi phí ẩn

Đọc `flowScope.orderDraft.customer.address.city` có vẻ đơn giản, nhưng nếu `orderDraft` là JPA entity chứa quan hệ lazy, getter có thể kích hoạt truy vấn. Đọc một collection rồi projection từng phần tử cũng có thể gây nhiều query hoặc `LazyInitializationException` nếu persistence context đã đóng.

Trong flow nhiều request, nên đưa dữ liệu cần render/điều hướng vào DTO gọn và tải theo service ở thời điểm phù hợp. Tránh lưu managed entity hoặc proxy trong scope dài hạn; tránh gọi method có side effect trong `test` vì engine có thể đánh giá expression ở những thời điểm không phù hợp để ghi dữ liệu.

## 9. Bảo mật khi expression truy cập giá trị lồng nhau

Expression được đánh giá ở server, nhưng nhiều giá trị trong model có nguồn gốc từ request. Đọc được một property không có nghĩa là người dùng có quyền thay đổi nó.

- Chỉ binding những property mà view hiện tại cho phép người dùng chỉnh.
- Không dùng `requestParameters.ownerId`, `requestParameters.role` hoặc field hidden làm căn cứ phân quyền.
- Không để biểu thức quyết định quyền sở hữu chỉ dựa trên ID trong flowScope; service phải đối chiếu principal hiện tại với bản ghi tin cậy.
- Không gọi method ghi dữ liệu trong `<if test="...">`; decision-state nên dùng điều kiện chỉ đọc.
- Tránh đưa token, mật khẩu hoặc thông tin thanh toán nhạy cảm vào object graph chỉ để view đọc.
- Escape dữ liệu khi render HTML; expression đọc đúng giá trị không bảo đảm đầu ra HTML an toàn.

Ví dụ điều kiện sau chỉ phù hợp cho **định tuyến giao diện**, không thay thế authorization:

~~~xml
<if test="flowScope.orderDraft.customer.email != null"
    then="reviewOrder"
    else="enterContact" />
~~~

Khi action xác nhận đơn, service phải tự kiểm tra người dùng hiện tại có quyền với order đó, giá và trạng thái còn hợp lệ, và thao tác có an toàn khi gửi lại hay không.

## 10. Kiểm thử expression với dữ liệu đại diện

Nên tạo fixture gồm object đầy đủ, object thiếu dữ liệu, collection rỗng, map thiếu key và phần tử null. Sau đó chạy flow qua event để kiểm tra kết quả expression.

| Ca kiểm thử | Dữ liệu | Điều cần xác minh |
|---|---|---|
| Nested property đầy đủ | `customer.address.city = 'Hanoi'` | Đọc đúng city và chọn nhánh tương ứng |
| Customer null | `customer = null` | Guard/safe navigation xử lý theo thiết kế |
| Address null | Customer có nhưng chưa có address | Không phát sinh lỗi property access ngoài dự kiến |
| List có phần tử | `items[0]` tồn tại | Đọc đúng quantity/product |
| List rỗng | `items = []` | Không truy cập `[0]` trước khi guard |
| Map có key | `attributes['channel'] = 'WEB'` | Đọc đúng value |
| Map thiếu key | Không có `channel` | Xử lý null theo hợp đồng |
| Selection | Một số line quantity bằng 0 | Chỉ giữ phần tử thỏa predicate |
| Projection | Nhiều product khác nhau | Trả list tên theo thứ tự nguồn |
| Property sai | `customer.mail` nhưng model chỉ có `email` | Test phát hiện lỗi expression khi flow được build/run |
| Collection chứa null | Một phần tử null | Không gọi property trên phần tử null |
| XML có toán tử `<` | Biểu thức được escape `&lt;` | Flow XML parse thành công |

### 10.1. Kiểm thử selection và projection riêng

Với list mẫu gồm ba dòng hàng có số lượng `2`, `0`, `5`, kỳ vọng:

- `items.?[quantity gt 0]` trả hai dòng hàng.
- `items.![product.name]` trả ba tên theo thứ tự ban đầu.
- `items.^[quantity gt 0]` trả dòng đầu tiên có số lượng dương.
- `items.$[quantity gt 0]` trả dòng cuối cùng có số lượng dương.

Nếu một phần tử có `product == null`, projection `product.name` có thể lỗi; fixture nên có test riêng hoặc dữ liệu được validate trước khi expression chạy.

### 10.2. Kiểm thử flow expression thay vì chỉ kiểm tra chuỗi

Một unit test so sánh chuỗi expression với expected string không chứng minh parser hiểu nó. Nên nạp flow definition bằng parser thực tế, khởi tạo scope với fixture, phát event dẫn đến state cần kiểm tra và assert state/outcome hoặc giá trị đã ghi vào scope.

Có thể dùng test support của Spring Web Flow (chẳng hạn `AbstractXmlFlowExecutionTests` ở phiên bản cung cấp API đó) để kiểm thử flow XML. Với expression có selection/projection hoặc safe navigation, phải chạy bằng **đúng parser và phiên bản** mà ứng dụng sử dụng. Kiểm thử Spring MVC riêng nếu cần xác minh URL execution, form binding, validation, session và view rendering.

## 11. Bài tập thực hành

Xây dựng flow xem lại đơn hàng với DTO `OrderDraft` có:

- `customer`: chứa `email` và `address.city`;
- `items`: danh sách `OrderLine`, mỗi dòng có `product.name`, `quantity`, `unitPrice`;
- `attributes`: map lưu `channel` và `campaign-code`.

Yêu cầu:

1. Dùng property path để đọc email và thành phố giao hàng.
2. Dùng indexer để đọc dòng hàng đầu tiên sau khi kiểm tra danh sách không null/rỗng.
3. Dùng map key notation để phân biệt đơn từ `WEB` và kênh khác.
4. Dùng selection để lọc các dòng có `quantity gt 0`.
5. Dùng projection để tạo danh sách tên sản phẩm cho view review.
6. Kiểm tra nested object null và map key không tồn tại bằng nhánh có chủ đích.
7. Viết một action chỉ đọc tính số dòng hợp lệ, lưu kết quả vào `flowScope`, rồi dùng decision-state ngắn để định tuyến.
8. Viết test cho list rỗng, phần tử null, map thiếu key, city null và parser không hỗ trợ cú pháp SpEL nâng cao.

**Tiêu chí hoàn thành:** người học giải thích được dấu chấm đọc property nào, bracket notation đang dùng index hay map key, selection khác projection ra sao, tại sao null và index cần guard, và vì sao expression nên ngắn, chỉ đọc, không thay thế service layer. Khi hiểu rõ các cấu trúc này, flow definition có thể diễn tả dữ liệu lồng nhau một cách rõ ràng mà vẫn dễ kiểm thử và bảo trì.

## Ghi chú tương thích

Các ví dụ collection selection/projection, safe navigation và toán tử so sánh sử dụng cú pháp SpEL. Cần xác nhận expression parser và phiên bản Spring được cấu hình trong ứng dụng. Nếu dùng Unified EL hoặc parser khác, chuyển biểu thức theo cú pháp tương ứng; không trộn cú pháp giữa các parser trong cùng flow mà không có cấu hình hỗ trợ.
