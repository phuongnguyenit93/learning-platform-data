# Gán và cập nhật dữ liệu bằng set

Trong một hành trình Spring Web Flow, dữ liệu được tạo ra ở nhiều thời điểm: khi flow bắt đầu, khi người dùng chọn một dòng kết quả, khi chuyển state hoặc khi một bước nghiệp vụ hoàn tất. Ta thường cần lưu một giá trị vào scope để state tiếp theo sử dụng, hoặc cập nhật một thuộc tính của object đã có trong flow. Thẻ **`<set>`** cung cấp cách ngắn gọn để thực hiện việc đó ngay trong flow definition.

Ví dụ, người dùng chọn một khách sạn từ danh sách kết quả. Flow cần lưu khách sạn đã chọn để màn hình tiếp theo hiển thị chi tiết. Hoặc người dùng thay đổi cách sắp xếp; flow cập nhật thuộc tính `sortBy` của đối tượng tiêu chí tìm kiếm đang tồn tại. Hai thao tác đều có thể diễn đạt bằng `<set>`, nhưng **đích gán**, **scope** và **thời điểm chạy** phải được xác định chính xác.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vai trò của `<set name="..." value="..."/>` trong Spring Web Flow.
2. Phân biệt biểu thức đích `name` với biểu thức nguồn `value`.
3. Tạo biến mới trong `flowScope`, `viewScope`, `requestScope`, `flashScope` và `conversationScope`.
4. Cập nhật thuộc tính của một biến/object đã tồn tại mà không tạo biến mới.
5. Chuyển đổi kiểu giá trị bằng thuộc tính `type`.
6. Chọn thời điểm gán phù hợp trong `on-start`, `on-entry`, `on-render` và `transition`.
7. Phân biệt `<set>` với `<evaluate>`, tránh ghi đè dữ liệu hoặc tin cậy mù quáng request parameter.
8. Kiểm thử việc gán và cập nhật dữ liệu qua các state.

## 2. Cú pháp cơ bản của set

Cú pháp thường dùng:

```xml
<set name="flowScope.sortMode" value="'recommended'" />
```

Thẻ `<set>` đánh giá biểu thức ở `value`, rồi gán kết quả vào biểu thức đích ở `name`. Có thể đọc theo cách:

```text
Đích nhận (name)       Nguồn giá trị (value)
flowScope.sortMode  <-  'recommended'
```

Hai thuộc tính có ý nghĩa khác nhau:

| Thuộc tính | Vai trò | Ví dụ |
| --- | --- | --- |
| `name` | Biểu thức xác định biến hoặc property sẽ được gán | `flowScope.sortMode` |
| `value` | Biểu thức cung cấp giá trị mới | `'recommended'` |
| `type` | Kiểu đích mong muốn để chuyển đổi giá trị nếu cần | `type="long"` |

`name` không phải một chuỗi tên biến đơn thuần trong mọi trường hợp. Nó có thể là đường dẫn property tới một object đang tồn tại, chẳng hạn `searchCriteria.sortBy`. `value` cũng không nhất thiết là literal; nó có thể đọc request parameter, scope variable, gọi property hoặc truy cập một kết quả khác trong flow.

### 2.1. Chuỗi literal cần đặt dấu nháy trong EL

Nếu muốn gán chuỗi cố định, hãy đặt dấu nháy đơn bên trong thuộc tính XML:

```xml
<set name="flashScope.statusMessage"
     value="'Đã lưu lựa chọn của bạn'" />
```

Nếu viết `value="Đã lưu lựa chọn của bạn"`, biểu thức có thể bị hiểu là tên biến/property thay vì literal chuỗi. Ngược lại, khi đọc giá trị từ biến, không bọc tên biến trong dấu nháy:

```xml
<!-- Đọc thuộc tính của request parameter. -->
<set name="requestScope.sortMode"
     value="requestParameters.sort" />
```

### 2.2. set luôn trả về event success

Trong Spring Web Flow, `SetAction` là action gán một thuộc tính vào scope và **luôn trả về event `success`** khi thực thi hoàn tất bình thường. Nếu đặt `<set>` trong một vị trí yêu cầu action outcome, transition có thể dùng `on="success"`.

Điều này không có nghĩa giá trị được gán là “đúng nghiệp vụ”. `success` chỉ cho biết action gán đã thực hiện xong; việc kiểm tra quyền, giới hạn giá trị hoặc lưu database vẫn thuộc trách nhiệm của ứng dụng.

## 3. Gán một biến mới vào scope

Khi tạo một biến mới, hãy chỉ rõ scope trong `name`. Ví dụ:

```xml
<flow xmlns="http://www.springframework.org/schema/webflow"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:schemaLocation="http://www.springframework.org/schema/webflow
                          https://www.springframework.org/schema/webflow/spring-webflow.xsd">

    <on-start>
        <set name="flowScope.sortMode" value="'recommended'" />
        <set name="flowScope.pageNumber" value="1" />
        <set name="flowScope.showArchived" value="false" />
    </on-start>

    <view-state id="searchResults" />
</flow>
```

Khi flow bắt đầu, ba biến được tạo trong flow scope. Các state về sau có thể đọc `sortMode`, `pageNumber` và `showArchived`.

Nếu không chỉ rõ scope khi gán một biến mới, Web Flow không thể biết cần tạo biến ở đâu. Vì vậy, quy tắc dễ nhớ là:

- **Tạo biến mới:** dùng prefix scope, ví dụ `flowScope.selectedHotel`.
- **Cập nhật property của biến đã có:** dùng property path của biến, ví dụ `searchCriteria.sortBy`.

### 3.1. Gán kết quả của một biểu thức

Giá trị có thể được lấy từ một biến hoặc Spring bean:

```xml
<set name="flowScope.selectedHotel"
     value="hotels.selectedRow" />
```

Ở đây `hotels.selectedRow` là giá trị nguồn, còn `flowScope.selectedHotel` là biến mới trong flow scope. Cách này thường dùng khi người dùng chọn một dòng trong bảng kết quả.

Nếu biểu thức nguồn trả về một object, `<set>` gán **tham chiếu tới object đó**. Nó không tự sao chép sâu (deep copy) object, cũng không biến entity thành DTO. Nếu hai biến cùng tham chiếu một object mutable, thay đổi qua một đường dẫn có thể được nhìn thấy ở đường dẫn còn lại.

## 4. Cập nhật thuộc tính của biến đã tồn tại

Đây là trường hợp quan trọng cần phân biệt với việc tạo biến mới. Giả sử flow đã khai báo `searchCriteria`:

```xml
<flow xmlns="http://www.springframework.org/schema/webflow">
    <var name="searchCriteria"
         class="com.example.search.SearchCriteria" />

    <view-state id="reviewHotels">
        <transition on="sort">
            <set name="searchCriteria.sortBy"
                 value="requestParameters.sortBy" />
        </transition>
    </view-state>
</flow>
```

`<var>` tạo biến `searchCriteria` trong flow scope. Khi cập nhật property `sortBy` của object này, `name` có thể là `searchCriteria.sortBy`. Không cần viết `flowScope.searchCriteria.sortBy`, bởi Web Flow có thể tìm biến đã tồn tại theo thuật toán tìm scope.

Tuy nhiên, viết rõ scope cũng có thể giúp người đọc hiểu nguồn gốc biến:

```xml
<set name="flowScope.searchCriteria.sortBy"
     value="requestParameters.sortBy" />
```

Điều quan trọng là `searchCriteria` phải tồn tại và property `sortBy` phải có thể ghi. `<set>` không tự tạo object cha còn `null` hoặc tự bổ sung setter Java bị thiếu.

### 4.1. Cập nhật một thuộc tính lồng nhau

Giả sử `booking` và `customer` đã được tạo:

```xml
<set name="booking.customer.preferredLanguage"
     value="requestParameters.language" />
```

Đích là property lồng nhau `preferredLanguage`. Để thao tác thành công, `booking` và `booking.customer` phải có giá trị phù hợp, và đường dẫn property phải truy cập/ghi được theo cơ chế EL.

Nếu `booking.customer` là `null`, thao tác có thể thất bại khi giải quyết property path. Hãy khởi tạo object con ở bước tạo model hoặc dùng service để chuẩn bị cấu trúc hợp lệ trước khi cập nhật.

### 4.2. Thay thế object và sửa property không giống nhau

| Cách gán | Ý nghĩa |
| --- | --- |
| `name="flowScope.selectedHotel"` | Gán/reassign biến `selectedHotel` trong flow scope |
| `name="searchCriteria.sortBy"` | Sửa property `sortBy` của object `searchCriteria` đang có |
| `name="flowScope.searchCriteria"` | Thay giá trị biến `searchCriteria` trong flow scope bằng object nguồn |
| `name="booking.customer.preferredLanguage"` | Sửa property lồng nhau của object đã tồn tại |

Khi thay thế cả object, các state khác có thể nhìn thấy object mới thay vì object cũ. Hãy cân nhắc liệu cần cập nhật một field hay cần thay toàn bộ model.

## 5. Chọn scope cho giá trị cần gán

Spring Web Flow cung cấp nhiều scope. Prefix được đặt trong biểu thức đích `name`:

| Scope | Vòng đời khái quát | Khi nào dùng |
| --- | --- | --- |
| `flowScope` | Từ lúc flow bắt đầu đến khi flow kết thúc | Model và lựa chọn cần dùng qua nhiều state |
| `viewScope` | Từ lúc vào một view-state đến khi rời state đó | Dữ liệu chỉ phục vụ một màn hình |
| `requestScope` | Trong một lượt request của flow | Giá trị trung gian chỉ cần trong lần xử lý hiện tại |
| `flashScope` | Được giữ cho đến sau lần render view kế tiếp, rồi được dọn | Thông báo ngắn sau hành động |
| `conversationScope` | Từ lúc top-level flow bắt đầu đến khi top-level flow kết thúc; chia sẻ với subflow | Dữ liệu thực sự cần chia sẻ trong cả conversation |

### 5.1. Flow scope

`flowScope` phù hợp với dữ liệu xuyên suốt một hành trình:

```xml
<set name="flowScope.booking"
     value="bookingService.createBooking(hotelId, currentUser.name)" />
```

Sau đó các state có thể đọc `booking` để hiển thị chi tiết, cập nhật lựa chọn hoặc xác nhận. Với cơ chế lưu trữ flow execution mặc định, object trong flow scope cần đáp ứng yêu cầu serialization; ưu tiên DTO/đối tượng có thể tuần tự hóa.

### 5.2. View scope

`viewScope` chỉ tồn tại trong vòng đời view-state hiện tại:

```xml
<view-state id="reviewHotels">
    <on-entry>
        <set name="viewScope.highlightedHotelId"
             value="flowScope.selectedHotel.id" />
    </on-entry>
</view-state>
```

Khi rời `reviewHotels`, view scope được giải phóng. Không dùng nó cho dữ liệu cần giữ khi flow chuyển sang state khác.

### 5.3. Request scope

Ví dụ đọc request parameter và chuyển thành số:

```xml
<set name="requestScope.hotelId"
     value="requestParameters.id"
     type="long" />
```

Giá trị này chỉ cần cho lượt xử lý hiện tại. Nếu state kế tiếp hoặc request kế tiếp cần sử dụng, hãy gán vào scope có vòng đời dài hơn sau khi đã kiểm tra hợp lệ.

### 5.4. Flash scope

Flash scope hữu ích cho thông báo hiển thị một lần:

```xml
<set name="flashScope.statusMessage"
     value="resourceBundle.bookingConfirmed" />
```

Flash scope được dọn sau khi view render. Nếu đặt message quá sớm và có một view render xen giữa, thông báo có thể không còn ở màn hình mà bạn dự định.

### 5.5. Conversation scope

Conversation scope được chia sẻ giữa top-level flow và các subflow của nó:

```xml
<set name="conversationScope.localeChoice"
     value="requestParameters.locale" />
```

Chỉ dùng khi dữ liệu thật sự cần được chia sẻ xuyên nhiều flow liên quan. Conversation scope không phải nơi chứa mọi biến dùng chung toàn ứng dụng; object được lưu trong session cần có khả năng serialization và phải được kiểm tra quyền/nguồn dữ liệu như các scope khác.

## 6. Đọc dữ liệu nguồn từ request và chuyển kiểu

Giá trị HTTP request thường đến dưới dạng chuỗi. Thuộc tính `type` của `<set>` cho phép yêu cầu chuyển đổi sang kiểu đích:

```xml
<set name="requestScope.hotelId"
     value="requestParameters.id"
     type="long" />

<set name="flowScope.pageSize"
     value="requestParameters.size"
     type="int" />
```

Ví dụ đầu tiên yêu cầu chuyển `requestParameters.id` sang kiểu long; ví dụ thứ hai chuyển sang integer. Nếu giá trị không thể chuyển đổi, action có thể phát sinh lỗi chuyển kiểu thay vì gán một giá trị hợp lệ.

**Chuyển kiểu không phải validation nghiệp vụ.** `hotelId=999999` có thể chuyển sang long thành công nhưng khách sạn đó có thể không tồn tại hoặc người dùng không có quyền truy cập. Hãy kiểm tra dữ liệu tại service trước khi dùng nó để thay đổi trạng thái nghiệp vụ.

### 6.1. Giới hạn giá trị được phép

Ví dụ người dùng chọn cách sắp xếp:

```xml
<transition on="sort">
    <set name="searchCriteria.sortBy"
         value="requestParameters.sortBy" />
</transition>
```

Không nên chấp nhận bất kỳ chuỗi nào từ request nếu nó có thể điều khiển truy vấn hoặc biểu thức động. Hãy kiểm tra giá trị thuộc tập được phép, chẳng hạn `price`, `rating` hoặc `name`. Việc allowlist có thể được thực hiện ở action/service trước khi cập nhật model, hoặc bằng validator phù hợp.

Một cách tách rõ trách nhiệm:

```xml
<transition on="sort">
    <evaluate expression="searchService.validateSort(requestParameters.sortBy)" />
    <set name="searchCriteria.sortBy"
         value="requestParameters.sortBy" />
</transition>
```

Ví dụ này chỉ phù hợp nếu `validateSort` có hợp đồng rõ và khi không hợp lệ nó ngăn thao tác theo cơ chế lỗi/validation của ứng dụng. Nếu validation không có tác dụng ngăn action tiếp theo, hãy dùng một action duy nhất để kiểm tra rồi cập nhật, hoặc cấu trúc thành state/event riêng.

## 7. Chọn đúng thời điểm thực thi set

Cùng một lệnh `<set>` nhưng đặt ở vị trí khác nhau sẽ tạo hành vi khác nhau. Các điểm thường dùng:

| Vị trí | Khi chạy | Trường hợp phù hợp |
| --- | --- | --- |
| `<on-start>` | Khi flow bắt đầu | Khởi tạo lựa chọn mặc định hoặc dữ liệu ban đầu |
| `<on-entry>` | Mỗi lần flow vào state | Chuẩn bị dữ liệu gắn với state |
| `<on-render>` | Mỗi lần view được render | Tính dữ liệu chỉ phục vụ lần render hiện tại |
| Bên trong `<transition>` | Khi event khớp transition đó | Cập nhật model theo lựa chọn của người dùng |
| `<on-exit>` | Khi rời state | Ghi nhận dữ liệu cần xử lý khi rời bước |
| `<on-end>` | Khi flow kết thúc | Gán dữ liệu tổng kết hoặc chuẩn bị output nếu cần |

### 7.1. Khởi tạo mặc định một lần

```xml
<on-start>
    <set name="flowScope.sortMode" value="'recommended'" />
    <set name="flowScope.pageNumber" value="1" />
</on-start>
```

Nếu người dùng chuyển state nhiều lần, `on-start` không chạy lại cho mỗi lần vào view. Đây là vị trí phù hợp cho giá trị mặc định của toàn flow.

### 7.2. Cập nhật theo event

```xml
<view-state id="reviewHotels">
    <transition on="sortByPrice">
        <set name="searchCriteria.sortBy" value="'price'" />
    </transition>
    <transition on="sortByRating">
        <set name="searchCriteria.sortBy" value="'rating'" />
    </transition>
</view-state>
```

Mỗi transition cập nhật một lựa chọn khác nhau. Nếu cần điều hướng sau khi set, có thể khai báo `to` trên transition:

```xml
<transition on="select" to="reviewHotel">
    <set name="flowScope.selectedHotel"
         value="hotels.selectedRow" />
</transition>
```

Trong ví dụ, việc chọn dòng kết quả gán object đang chọn vào flow scope trước khi flow đi tới state `reviewHotel`.

### 7.3. Cẩn thận khi đặt set trong on-render

```xml
<view-state id="editSearch">
    <on-render>
        <set name="viewScope.sortMode"
             value="flowScope.sortMode" />
    </on-render>
</view-state>
```

`on-render` có thể chạy lại khi view được render nhiều lần, chẳng hạn sau validation error hoặc Ajax refresh. Nếu mỗi lần render đều gán lại dữ liệu do người dùng đang chỉnh sửa, giá trị vừa nhập có thể bị ghi đè. Chỉ đặt `<set>` ở đây khi việc tính/gán lại thực sự cần diễn ra ở **mỗi lần render**.

## 8. Ví dụ hoàn chỉnh: tìm khách sạn và lưu lựa chọn

Flow dưới đây minh họa một luồng tìm khách sạn:

1. Nhận `city` khi flow bắt đầu.
2. Tạo `searchCriteria` và thiết lập sắp xếp mặc định.
3. Hiển thị danh sách.
4. Người dùng đổi cách sắp xếp hoặc chọn một khách sạn.
5. Lưu khách sạn được chọn vào flow scope để màn hình chi tiết dùng.

### 8.1. Flow definition

```xml
<flow xmlns="http://www.springframework.org/schema/webflow"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:schemaLocation="http://www.springframework.org/schema/webflow
                          https://www.springframework.org/schema/webflow/spring-webflow.xsd">

    <input name="city" required="true" />

    <var name="searchCriteria"
         class="com.example.hotel.SearchCriteria" />

    <on-start>
        <set name="searchCriteria.city" value="city" />
        <set name="searchCriteria.sortBy" value="'recommended'" />
        <set name="flowScope.pageNumber" value="1" />
    </on-start>

    <view-state id="reviewHotels">
        <on-render>
            <evaluate
                expression="hotelService.findHotels(searchCriteria)"
                result="viewScope.hotels"
                result-type="dataModel" />
        </on-render>

        <transition on="sortByPrice">
            <set name="searchCriteria.sortBy" value="'price'" />
        </transition>

        <transition on="sortByRating">
            <set name="searchCriteria.sortBy" value="'rating'" />
        </transition>

        <transition on="select" to="reviewHotel">
            <set name="flowScope.selectedHotel"
                 value="hotels.selectedRow" />
        </transition>
    </view-state>

    <view-state id="reviewHotel">
        <transition on="back" to="reviewHotels" />
        <transition on="book" to="booking">
            <set name="flowScope.bookingHotelId"
                 value="selectedHotel.id" />
        </transition>
    </view-state>

    <end-state id="booking" />
</flow>
```

`<var>` tạo `searchCriteria` trong flow scope của flow khai báo nó. Các lệnh `set` trong `on-start` cập nhật hai property của object đã tồn tại và tạo một biến mới `pageNumber`. Khi người dùng chọn khách sạn, `hotels.selectedRow` được lưu vào `flowScope.selectedHotel`; khi nhấn đặt phòng, ID của khách sạn được sao chép sang biến `bookingHotelId` để bước tiếp theo dùng.

Ví dụ giả định `hotelService.findHotels` trả về đối tượng tương thích `dataModel` và view phát đúng các event `sortByPrice`, `sortByRating`, `select`. Khi quay lại `reviewHotels`, `on-render` tải danh sách theo `searchCriteria` mới nhất.

### 8.2. Luồng dữ liệu theo thời gian

| Thời điểm | Đích `name` | Nguồn `value` | Kết quả |
| --- | --- | --- | --- |
| Bắt đầu flow | `searchCriteria.city` | `city` | Cập nhật tiêu chí thành phố |
| Bắt đầu flow | `searchCriteria.sortBy` | `'recommended'` | Đặt cách sắp xếp mặc định |
| Bắt đầu flow | `flowScope.pageNumber` | `1` | Tạo biến trang mới |
| Event sortByPrice | `searchCriteria.sortBy` | `'price'` | Cập nhật object hiện có |
| Event select | `flowScope.selectedHotel` | `hotels.selectedRow` | Lưu object được chọn |
| Event book | `flowScope.bookingHotelId` | `selectedHotel.id` | Tạo giá trị ID cho bước kế tiếp |

### 8.3. Vì sao danh sách hotels ở view scope?

Danh sách kết quả được tải để render `reviewHotels`. Nếu rời state, dữ liệu `viewScope.hotels` không còn cần thiết; flow chỉ giữ `searchCriteria` và `selectedHotel` trong flow scope. Điều này giúp phân biệt:

- Dữ liệu phục vụ một lần render/state: `viewScope`.
- Dữ liệu cần cho nhiều state: `flowScope`.

## 9. set và evaluate: chọn đúng công cụ

Hai thẻ đều làm việc với biểu thức EL, nhưng mục đích chính khác nhau.

| Tiêu chí | `<set>` | `<evaluate>` |
| --- | --- | --- |
| Mục đích chính | Gán kết quả biểu thức vào một biến/property đích | Đánh giá biểu thức, thường gọi phương thức/action |
| Thuộc tính đích | `name` | `result` nếu muốn lưu kết quả |
| Biểu thức nguồn | `value` | `expression` |
| Ví dụ | `<set name="flowScope.page" value="1"/>` | `<evaluate expression="hotelService.findHotels(criteria)" result="viewScope.hotels"/>` |
| Outcome khi chạy như action | `success` | Phụ thuộc kết quả/action outcome |

### 9.1. Dùng set khi thao tác là phép gán

```xml
<set name="flowScope.pageNumber" value="1" />
<set name="searchCriteria.sortBy" value="'price'" />
<set name="flashScope.message" value="resourceBundle.saved" />
```

Các ví dụ trên đều biểu đạt “lấy giá trị này và gán vào đích kia”.

### 9.2. Dùng evaluate khi cần gọi service

```xml
<evaluate expression="hotelService.findHotels(searchCriteria)"
          result="viewScope.hotels"
          result-type="dataModel" />
```

Ở đây mục tiêu chính là gọi `hotelService.findHotels` để lấy danh sách. Kết quả được lưu vào `viewScope.hotels`. Nếu dùng `set` với một biểu thức gọi bean, nó vẫn có thể đánh giá được giá trị, nhưng `<evaluate>` thể hiện rõ đây là một thao tác gọi service và có thêm các tùy chọn dành cho action như `result-type`.

### 9.3. Đừng dùng set để thay thế thao tác nghiệp vụ

```xml
<!-- Không phải cách thay thế cho một giao dịch đặt phòng. -->
<set name="flowScope.bookingConfirmed" value="true" />
```

Đặt một cờ `true` không có nghĩa database đã ghi nhận đặt phòng. Việc lưu, kiểm tra tồn phòng, khóa tài nguyên và transaction phải được thực hiện ở service. Sau khi service xác nhận thành công, flow mới có thể gán cờ hoặc kết quả hiển thị nếu thực sự cần.

## 10. Cập nhật collection và dữ liệu được chọn

`<set>` có thể gán một object được lấy từ collection, ví dụ `hotels.selectedRow`, vào một biến khác:

```xml
<transition on="select" to="reviewHotel">
    <set name="flowScope.selectedHotel"
         value="hotels.selectedRow" />
</transition>
```

Đây là cách lưu phần tử đã chọn để state tiếp theo dùng. Tuy nhiên, `<set>` không tự động có nghĩa “thêm một phần tử vào List” hoặc “sao chép collection”. Nếu cần gọi phương thức thay đổi collection, dùng `<evaluate>` để biểu đạt thao tác đó:

```xml
<transition on="addGuest">
    <evaluate expression="booking.guests.add(currentEvent.attributes.guest)" />
</transition>
```

Phần tử được thêm ở ví dụ trên là object được chuyển trong event. Hãy xác thực kiểu, quyền và giới hạn số phần tử trước khi thêm. Nếu chỉ muốn giữ một lựa chọn tạm thời, gán phần tử vào một biến scope thường rõ ràng hơn việc thay đổi collection gốc.

### 10.1. Chú ý tham chiếu object

Nếu `selectedHotel` và một phần tử trong `hotels` là cùng một object, thay đổi một property qua `selectedHotel` có thể làm object trong danh sách thay đổi theo. `<set>` không tạo bản sao độc lập.

Khi cần snapshot của lựa chọn, hãy yêu cầu service tạo DTO hoặc immutable value object chứa các trường cần giữ. Không lưu toàn bộ object graph lớn chỉ để hiển thị một vài thông tin ở state sau.

## 11. Những lỗi thường gặp khi dùng set

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `EvaluationException` khi gán biến mới | `name` không có scope prefix | Dùng `flowScope.foo` hoặc scope phù hợp |
| Không cập nhật được `searchCriteria.sortBy` | `searchCriteria` chưa tồn tại hoặc property không ghi được | Kiểm tra `<var>`/khởi tạo model và setter |
| Lỗi khi gán nested property | Object cha/con đang `null` | Khởi tạo cấu trúc object trước khi set |
| Giá trị thành chuỗi thay vì số | Thiếu/không đúng `type` hoặc conversion config | Dùng `type` và kiểm tra converter |
| Lỗi chuyển kiểu từ request | Giá trị người dùng không hợp lệ | Validate request, hiển thị message và không dùng dữ liệu chưa kiểm tra |
| Giá trị bị reset sau khi render | `set` nằm trong `on-render` hoặc `on-entry` chạy lại | Chọn lại thời điểm thực thi |
| State sau không thấy biến | Gán vào `viewScope` hoặc `requestScope` có vòng đời ngắn | Chuyển sang `flowScope` nếu cần giữ qua state |
| Thông báo biến mất trước khi hiển thị | Gán `flashScope` quá sớm, có render xen giữa | Gán gần lần render cần thông báo |
| Dữ liệu thay đổi ở nhiều nơi cùng lúc | `set` gán cùng tham chiếu object mutable | Dùng DTO/snapshot nếu cần độc lập |
| Giá trị request làm sai trạng thái nghiệp vụ | Tin cậy request parameter mà không kiểm tra | Allowlist và xác minh ở service |

### 11.1. Scope prefix bị thiếu

Sai:

```xml
<set name="selectedHotel" value="hotels.selectedRow" />
```

Nếu `selectedHotel` chưa tồn tại trong scope, Web Flow không biết phải tạo nó ở đâu. Sửa:

```xml
<set name="flowScope.selectedHotel"
     value="hotels.selectedRow" />
```

### 11.2. Dùng scope quá ngắn

Sai nếu cần dùng ở state tiếp theo:

```xml
<set name="viewScope.selectedHotel"
     value="hotels.selectedRow" />
```

Khi rời view-state, `viewScope` được giải phóng. Nếu state sau cần object này, dùng:

```xml
<set name="flowScope.selectedHotel"
     value="hotels.selectedRow" />
```

### 11.3. Gán property trên object chưa tồn tại

Nếu `booking.customer` đang `null`, lệnh sau không thể tự đảm bảo tạo object con:

```xml
<set name="booking.customer.preferredLanguage"
     value="'vi'" />
```

Hãy khởi tạo `customer` trong service hoặc tạo model trước khi cập nhật:

```java
if (booking.getCustomer() == null) {
    booking.setCustomer(new Customer());
}
```

## 12. An toàn dữ liệu và trách nhiệm của service

`<set>` là công cụ thay đổi trạng thái. Nếu nguồn `value` đến từ request, người dùng có thể thử gửi giá trị ngoài dự kiến. Vì vậy:

1. Chỉ cho phép các giá trị trong tập hợp hợp lệ, ví dụ `sortBy` chỉ nhận `price`, `rating` hoặc `name`.
2. Không gán trực tiếp request parameter vào thuộc tính quyết định giá, quyền, trạng thái thanh toán hoặc chủ sở hữu.
3. Dùng service để xác minh tài nguyên thuộc người dùng hiện tại trước khi lưu lựa chọn.
4. Tránh đưa secret/token hoặc dữ liệu nhạy cảm vào scope chỉ vì tiện truy cập từ EL.
5. Dùng `flowScope` cho dữ liệu cần xuyên nhiều state, nhưng không xem nó là kho lưu trữ nghiệp vụ bền vững.
6. Nếu một action cập nhật database, hãy đặt transaction ở service và thiết kế idempotency cho thao tác có thể bị gửi lặp.

Ví dụ, không nên viết:

```xml
<set name="flowScope.order.total"
     value="requestParameters.total" />
```

Tổng tiền phải được tính từ dữ liệu đơn hàng và giá tin cậy ở server, không nhận từ trình duyệt.

## 13. Kiểm thử các thao tác gán

Spring Web Flow cung cấp hỗ trợ kiểm thử flow qua `AbstractXmlFlowExecutionTests`. Có thể bắt đầu flow, phát event và kiểm tra state/outcome; để xác minh giá trị scope, có thể truy cập context trong test theo API của phiên bản đang dùng.

### 13.1. Ma trận kiểm thử

| Ca kiểm thử | Tác động | Kỳ vọng |
| --- | --- | --- |
| Khởi tạo flow | `on-start` gán `flowScope.pageNumber=1` | Giá trị mặc định có trong flow scope |
| Cập nhật object | Event `sortByPrice` | `searchCriteria.sortBy` là `price` |
| Chọn phần tử | Event `select` | `selectedHotel` là phần tử được chọn |
| Gán request parameter có type | `id="42"` và `type="long"` | Giá trị đích là Long |
| Request sai kiểu | `id="abc"` | Chuyển kiểu thất bại có kiểm soát |
| Scope ngắn | Gán vào `viewScope` rồi rời state | Không kỳ vọng biến còn tồn tại ở state khác |
| Flash message | Gán trước view cần hiển thị | Message tồn tại đến lần render mục tiêu |
| Nested object null | Property cha chưa khởi tạo | Test phát hiện lỗi và xác nhận bước khởi tạo |
| Giá trị không allowlist | `sortBy=sqlFragment` | Service/validation từ chối |
| Gán object mutable | Hai biến cùng tham chiếu object | Test xác nhận hành vi chia sẻ tham chiếu được hiểu rõ |

### 13.2. Ví dụ flow test

Đoạn dưới đây minh họa cấu trúc kiểm thử; cần cấu hình XML resource và dependency test của dự án:

```java
public class HotelSearchFlowTests
        extends AbstractXmlFlowExecutionTests {

    @Override
    protected String getResourceLocation() {
        return "classpath:flows/hotel-search.xml";
    }

    public void testSelectHotelMovesToReview() {
        startFlow(new LocalAttributeMap("city", "Hanoi"),
                  new MockExternalContext());

        assertCurrentStateEquals("reviewHotels");

        // Test fixture cần cung cấp DataModel với selectedRow phù hợp.
        signalEvent("select");

        assertCurrentStateEquals("reviewHotel");
    }
}
```

Test state transition là bước đầu; để chứng minh `<set>` đã gán đúng giá trị, hãy kiểm tra flow execution context hoặc quan sát dữ liệu qua state tiếp theo bằng assertion phù hợp với API test. Không nên chỉ assert rằng view mới được mở rồi kết luận dữ liệu đã đúng.

### 13.3. Kiểm thử hành vi lặp lại

Nếu `<set>` nằm trong `on-render` hoặc `on-entry`, test cần render/đi vào state nhiều lần và xác nhận nó có ghi đè giá trị hay không. Đây là cách phát hiện lỗi “người dùng vừa chọn xong nhưng giá trị quay lại mặc định”.

## 14. Bài tập thực hành

Hãy xây dựng flow `hotel-search`:

1. Nhận input `city` khi bắt đầu.
2. Tạo `SearchCriteria` trong flow scope.
3. Dùng `<set>` để gán `city`, `sortBy='recommended'` và `pageNumber=1`.
4. Tại state `reviewHotels`, cho phép event `sortByPrice` và `sortByRating` cập nhật property `sortBy`.
5. Khi người dùng chọn một khách sạn, lưu `hotels.selectedRow` vào `flowScope.selectedHotel`.
6. Ở state chi tiết, tạo `flashScope.statusMessage` để hiển thị thông báo khi đặt phòng thành công.
7. Viết test cho giá trị mặc định, đổi sắp xếp, chọn khách sạn, request parameter sai kiểu và thông báo flash.

**Câu hỏi tự kiểm tra:**

- Vì sao `<set name="selectedHotel" .../>` không phải cách rõ ràng để tạo biến mới?
- Khi nào dùng `searchCriteria.sortBy` và khi nào dùng `flowScope.searchCriteria`?
- Nếu `set` nằm trong `on-render`, điều gì xảy ra khi view render lại sau validation error?
- Vì sao gán `requestParameters.total` vào `flowScope.order.total` là thiết kế không an toàn?
- Nếu `selectedHotel` và `hotels.selectedRow` cùng tham chiếu một object, thay đổi object ở một nơi có thể ảnh hưởng nơi còn lại thế nào?

## 15. Những điểm cần nhớ

- `<set>` đánh giá biểu thức `value` rồi gán kết quả vào biểu thức đích `name`.
- Tạo biến mới phải chỉ rõ scope trong `name`, ví dụ `flowScope.selectedHotel`; cập nhật property của biến đã tồn tại có thể dùng property path trực tiếp, ví dụ `searchCriteria.sortBy`.
- `type` hỗ trợ chuyển kiểu giá trị nguồn, nhưng không thay thế validation hoặc kiểm tra quyền nghiệp vụ.
- `on-start` phù hợp cho giá trị mặc định của flow; transition phù hợp cho cập nhật theo event; `on-render` có thể chạy nhiều lần và dễ ghi đè dữ liệu nếu đặt không đúng.
- `viewScope` và `requestScope` có vòng đời ngắn; `flowScope` giữ dữ liệu qua các state; `conversationScope` chia sẻ trong top-level flow và subflow; `flashScope` dành cho dữ liệu tạm tới lần render.
- `<set>` không sao chép sâu object và không tự lưu database. Nếu cần gọi service hoặc thay đổi collection bằng phương thức, `<evaluate>` thường thể hiện ý định rõ hơn.
- Kiểm tra request data, giới hạn giá trị được phép và thực hiện quy tắc nghiệp vụ tại service trước khi tin dữ liệu đã gán.

### Tài liệu tham khảo

- [Spring Web Flow 3.0 Reference Guide — Special EL Variables và Scopes](https://docs.spring.io/spring-webflow/docs/3.0.0/reference/#_special_el_variables)
- [Spring Web Flow 3.0 Reference Guide — Actions và các điểm thực thi action](https://docs.spring.io/spring-webflow/docs/3.0.0/reference/#_actions)
- [Spring Web Flow 3.0 Reference Guide — Rendering Views, on-render và Transition Actions](https://docs.spring.io/spring-webflow/docs/3.0.0/reference/#_rendering_views)
- [SetAction Javadoc — Spring Web Flow 3.0.1](https://docs.spring.io/spring-webflow/docs/3.0.1/api/org/springframework/webflow/action/SetAction.html)
- [Action Javadoc — Spring Web Flow 3.0.1](https://docs.spring.io/spring-webflow/docs/3.0.1/api/org/springframework/webflow/execution/Action.html)
