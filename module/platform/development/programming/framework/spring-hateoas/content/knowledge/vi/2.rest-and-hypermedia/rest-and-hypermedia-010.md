# Mức độ trưởng thành Richardson

Mức độ trưởng thành Richardson (Richardson Maturity Model, thường viết tắt là RMM) là mô hình dùng để đánh giá cách một API Web tận dụng các đặc tính của HTTP và hypermedia. Mô hình chia cách thiết kế API thành bốn mức, từ mức 0 đến mức 3. Mỗi mức thể hiện một bước tiến trong cách client tương tác với server: từ gọi một endpoint kiểu RPC, đến định danh tài nguyên, sử dụng ngữ nghĩa HTTP, rồi khám phá hành động thông qua liên kết hypermedia.

Trong module Spring HATEOAS, RMM giúp xác định vai trò của thư viện: Spring HATEOAS hỗ trợ rõ nhất cho mức 3, nơi biểu diễn tài nguyên mang các liên kết và affordance để client khám phá bước tiếp theo. Tuy vậy, thêm dependency hoặc trả về JSON có trường `_links` chưa tự động khiến API đạt mức 3. Điều quan trọng là client có thể sử dụng các quan hệ hypermedia để điều hướng và thực hiện workflow mà không phải tự mã hóa cấu trúc URI của server.

Sau bài học, bạn có thể:

- Giải thích bốn mức 0, 1, 2 và 3 của Richardson Maturity Model.
- Phân biệt việc phân tách URI theo tài nguyên, sử dụng HTTP method đúng ngữ nghĩa và cung cấp hypermedia controls.
- Đánh giá một workflow API đang ở mức nào và nhận diện bước cải thiện phù hợp.
- Dùng Spring HATEOAS để tạo biểu diễn tài nguyên có link theo trạng thái nghiệp vụ.
- Kiểm thử link, media type và khả năng điều hướng của phản hồi HAL.

## 1. Richardson Maturity Model là gì?

Leonard Richardson giới thiệu mô hình này như một cách diễn giải mức độ sử dụng các ý tưởng của Web trong thiết kế API. Martin Fowler phổ biến mô hình qua bài viết về Richardson Maturity Model. Mô hình có bốn mức:

| Mức | Tên thường gọi | Đặc điểm chính |
|---|---|---|
| 0 | The Swamp of POX | Một endpoint hoặc một điểm gọi tập trung; HTTP chủ yếu làm phương tiện truyền tải |
| 1 | Resources | Nhiều URI định danh các tài nguyên khác nhau |
| 2 | HTTP Verbs | Kết hợp URI tài nguyên với HTTP method và status code có ngữ nghĩa phù hợp |
| 3 | Hypermedia Controls | Biểu diễn chứa link và thông tin điều khiển để client khám phá trạng thái tiếp theo |

RMM là mô hình đánh giá thực hành, không phải một tiêu chuẩn chứng nhận REST chính thức. Nó tập trung vào cách API sử dụng tài nguyên, HTTP và hypermedia. Một API ở mức 3 vẫn cần xem xét các ràng buộc REST khác như client-server, stateless, cache, layered system và (tùy chọn) code-on-demand. Vì vậy, không nên dùng một con số RMM duy nhất để khẳng định toàn bộ chất lượng hoặc mức tuân thủ REST của hệ thống.

Để hiểu các mức, ta sẽ dùng cùng một nghiệp vụ: khách hàng đặt một khung giờ khám với bác sĩ, xem lịch đặt và hủy lịch khi còn đủ điều kiện.

## 2. Mức 0 — The Swamp of POX

Ở mức 0, client gọi một endpoint tập trung và gửi thông tin về hành động cần thực hiện trong phần thân request. Server thường phân biệt các thao tác bằng trường action hoặc cấu trúc payload. HTTP được dùng chủ yếu như một đường truyền để chuyển thông điệp. Tên gọi The Swamp of POX bắt nguồn từ cụm Plain Old XML, nhưng ví dụ hiện đại có thể dùng JSON hoặc định dạng payload khác.

Ví dụ:

~~~http
POST /appointmentService HTTP/1.1
Content-Type: application/json

{
  "action": "book",
  "doctorId": "doctor-17",
  "slotId": "slot-42",
  "patientId": "patient-8"
}
~~~

Để xem lịch đã đặt, client vẫn gửi POST đến cùng endpoint:

~~~http
POST /appointmentService HTTP/1.1
Content-Type: application/json

{
  "action": "getBooking",
  "bookingId": "booking-99"
}
~~~

Để hủy lịch, client tiếp tục gọi cùng endpoint và đổi giá trị action thành cancel. Một endpoint có thể chứa nhiều nhánh xử lý, gần giống gọi một hàm từ xa (RPC).

Đặc điểm của mức 0:

- Một URI tập trung có thể xử lý nhiều thao tác nghiệp vụ khác nhau.
- Ý nghĩa thao tác chủ yếu nằm trong payload.
- Client và server phải thống nhất cấu trúc action và cách diễn giải payload.
- HTTP method, status code và cache thường chưa được tận dụng đầy đủ theo ngữ nghĩa của chúng.

Cách tiếp cận này không phải lúc nào cũng vô dụng. RPC qua HTTP có thể phù hợp với một số hệ thống nội bộ hoặc giao thức lệnh chuyên biệt. Tuy nhiên, nếu mục tiêu là thiết kế API tài nguyên theo phong cách REST, mức 0 chưa tận dụng được cách Web định danh và thao tác với tài nguyên.

## 3. Mức 1 — Resources

Mức 1 đưa tài nguyên vào thiết kế API. Thay vì dùng một URI cho toàn bộ thao tác, server công bố các URI khác nhau để định danh những tài nguyên có ý nghĩa trong miền nghiệp vụ.

Với hệ thống đặt lịch, có thể có các URI:

- `/doctors/doctor-17` định danh bác sĩ.
- `/slots/slot-42` định danh khung giờ.
- `/patients/patient-8` định danh bệnh nhân.
- `/bookings/booking-99` định danh một lịch đặt.

Client có thể tương tác với các tài nguyên qua các URI riêng. Tuy nhiên, ở mức 1, việc tách URI chưa bảo đảm HTTP method được sử dụng nhất quán. Một API có nhiều URI nhưng vẫn gửi mọi lệnh qua POST với trường action vẫn chủ yếu thể hiện đặc điểm của mức 1.

Ví dụ, server có thể phân biệt các đích tài nguyên:

~~~http
POST /slots/slot-42 HTTP/1.1
Content-Type: application/json

{
  "action": "book",
  "patientId": "patient-8"
}
~~~

~~~http
POST /bookings/booking-99 HTTP/1.1
Content-Type: application/json

{
  "action": "cancel"
}
~~~

Các URI đã mô tả đối tượng mà client muốn làm việc, nhưng ý nghĩa thao tác vẫn còn phụ thuộc vào payload. Client cũng có thể phải biết trước cấu trúc đường dẫn và cách tạo URI cho tài nguyên liên quan.

Mức 1 cải thiện khả năng nhận diện và tổ chức tài nguyên. Nó tạo nền tảng để mỗi tài nguyên có biểu diễn riêng và để các thao tác ở mức tiếp theo tận dụng đúng ngữ nghĩa HTTP.

## 4. Mức 2 — HTTP Verbs

Mức 2 kết hợp URI tài nguyên với các HTTP method có ngữ nghĩa phù hợp. Server dùng method để thể hiện loại thao tác, dùng status code để mô tả kết quả, và có thể dùng header để cung cấp metadata về biểu diễn, cache hoặc phiên bản tài nguyên.

Ví dụ với workflow đặt lịch:

**Đọc một khung giờ**

~~~http
GET /slots/slot-42 HTTP/1.1
Accept: application/json
~~~

Server trả về:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "id": "slot-42",
  "doctorId": "doctor-17",
  "available": true
}
~~~

**Tạo lịch đặt**

~~~http
POST /bookings HTTP/1.1
Content-Type: application/json

{
  "slotId": "slot-42",
  "patientId": "patient-8"
}
~~~

Nếu tạo thành công, server có thể trả về:

~~~http
HTTP/1.1 201 Created
Location: /bookings/booking-99
Content-Type: application/json

{
  "id": "booking-99",
  "status": "CONFIRMED"
}
~~~

**Đọc lịch đặt**

~~~http
GET /bookings/booking-99 HTTP/1.1
Accept: application/json
~~~

**Hủy lịch đặt**

~~~http
DELETE /bookings/booking-99 HTTP/1.1
~~~

Trong thực tế, hủy lịch có thể được mô hình hóa bằng DELETE nếu nghiệp vụ xem lịch đặt là tài nguyên bị xóa, hoặc bằng POST đến một tài nguyên hành động như `/bookings/booking-99/cancellation` nếu việc hủy tạo ra một bản ghi nghiệp vụ cần lưu lại. Điều quan trọng là method và URI phản ánh đúng ngữ nghĩa được công bố, không phải ép mọi nghiệp vụ vào một khuôn mẫu duy nhất.

### 4.1. Ý nghĩa của các HTTP method

| Method | Ngữ nghĩa thường dùng | Tính chất quan trọng |
|---|---|---|
| GET | Lấy biểu diễn của tài nguyên | Safe và idempotent |
| HEAD | Lấy metadata tương tự GET nhưng không có response body | Safe và idempotent |
| POST | Gửi dữ liệu để xử lý hoặc tạo tài nguyên phụ thuộc | Không mặc định idempotent |
| PUT | Tạo hoặc thay thế biểu diễn tại URI đích | Idempotent |
| PATCH | Áp dụng thay đổi một phần | Không mặc định idempotent |
| DELETE | Yêu cầu xóa tài nguyên | Idempotent theo ngữ nghĩa HTTP |

Safe nghĩa là client không yêu cầu server thực hiện thay đổi trạng thái nghiệp vụ khi gọi method đó. Idempotent nghĩa là thực hiện cùng một request nhiều lần có cùng hiệu ứng dự kiến lên trạng thái server như thực hiện một lần. Ví dụ, DELETE có thể trả 204 ở lần đầu và 404 ở lần sau nhưng vẫn có tính idempotent vì tài nguyên cuối cùng vẫn ở trạng thái đã bị xóa.

Không nên suy ra tính idempotent chỉ từ việc request có cùng payload. Nếu client gửi POST tạo lịch đặt hai lần, server có thể tạo hai lịch. Khi cần hỗ trợ retry an toàn, API có thể thiết kế idempotency key hoặc một cơ chế định danh request riêng.

### 4.2. Status code và header làm rõ hợp đồng

Mức 2 cũng tận dụng status code để client hiểu kết quả ở mức giao thức:

- 200 OK: request thành công và có biểu diễn phản hồi.
- 201 Created: một tài nguyên đã được tạo; Location thường trỏ đến tài nguyên mới.
- 202 Accepted: request đã được chấp nhận để xử lý bất đồng bộ.
- 204 No Content: request thành công nhưng không có response body.
- 400 Bad Request: request không hợp lệ.
- 404 Not Found: không tìm thấy tài nguyên đích.
- 409 Conflict: request xung đột với trạng thái hiện tại của tài nguyên.
- 412 Precondition Failed: điều kiện trong request, chẳng hạn If-Match, không được thỏa mãn.

Header cũng góp phần làm thông điệp tự mô tả:

- Content-Type cho biết định dạng biểu diễn server gửi.
- Accept cho biết các định dạng client có thể nhận.
- Location xác định vị trí tài nguyên được tạo hoặc chuyển hướng đến.
- ETag định danh phiên bản của biểu diễn.
- If-Match cho phép client yêu cầu cập nhật chỉ khi phiên bản tài nguyên chưa thay đổi.
- Cache-Control mô tả chính sách lưu cache.

Mức 2 giúp API có ngữ nghĩa HTTP rõ ràng và tận dụng được khả năng cache, retry, điều kiện cập nhật cũng như công cụ HTTP phổ biến. Tuy nhiên, client vẫn có thể phải tự xây URI từ mẫu đường dẫn, ID và tài liệu API. Nó biết cách gọi từng endpoint vì đã được lập trình sẵn, chứ chưa nhất thiết khám phá được hành động tiếp theo từ phản hồi.

## 5. Mức 3 — Hypermedia Controls

Mức 3 bổ sung hypermedia controls vào biểu diễn tài nguyên. Server không chỉ trả dữ liệu và địa chỉ của tài nguyên hiện tại; server còn cung cấp các liên kết có quan hệ ngữ nghĩa để client khám phá tài nguyên liên quan và các hành động khả dụng.

Ví dụ, client đọc lịch đặt:

~~~http
GET /bookings/booking-99 HTTP/1.1
Accept: application/hal+json
~~~

Server trả về HAL:

~~~http
HTTP/1.1 200 OK
Content-Type: application/hal+json

{
  "id": "booking-99",
  "status": "CONFIRMED",
  "appointmentTime": "2026-12-03T09:30:00+07:00",
  "_links": {
    "self": {
      "href": "https://api.example.com/bookings/booking-99"
    },
    "patient": {
      "href": "https://api.example.com/patients/patient-8"
    },
    "slot": {
      "href": "https://api.example.com/slots/slot-42"
    },
    "cancel": {
      "href": "https://api.example.com/bookings/booking-99/cancellation"
    }
  }
}
~~~

Client tìm relation `cancel` để biết biểu diễn hiện tại có cung cấp khả năng hủy lịch. Client dùng href được cung cấp để gửi request theo hợp đồng đã công bố. Nó không cần tự nối `/bookings/` với ID rồi đoán đường dẫn hủy. Trong HAL cơ bản, link chủ yếu cung cấp relation và href; nếu client cần tự khám phá cả HTTP method hoặc cấu trúc body thì API cần thêm affordance hoặc một hợp đồng thao tác được công bố phù hợp.

Sau khi lịch đã diễn ra, server có thể trả về cùng tài nguyên với trạng thái COMPLETED và bỏ link cancel. Có thể thay vào đó xuất hiện link `receipt` hoặc `feedback`. Biểu diễn vì thế phản ánh các chuyển trạng thái có thể thực hiện ở thời điểm client đọc tài nguyên.

### 5.1. Link là điều khiển, không chỉ là đường dẫn

Một link hypermedia có ít nhất hai thành phần:

- `href`: URI đích để client truy cập.
- `rel`: quan hệ mô tả ý nghĩa của link đối với tài nguyên hiện tại.

Một số relation phổ biến gồm `self`, `next`, `prev`, `first`, `last` và `collection`. Các relation theo miền như `cancel`, `approve`, `submit` hoặc `receipt` cần được định nghĩa rõ để client có thể hiểu ý nghĩa ổn định.

Client nên tìm link theo relation và sử dụng href như một giá trị opaque. Không nên phân tích href để lấy ID, phụ thuộc vào thứ tự link hoặc tự ghép thêm path segment. Nếu URI thay đổi nhưng relation giữ nguyên ý nghĩa, client có thể tiếp tục hoạt động mà không cần biết cấu trúc định tuyến mới.

### 5.2. Link phản ánh khả năng tại thời điểm hiện tại

Server có thể tạo link theo trạng thái nghiệp vụ, quyền của người dùng hoặc các điều kiện khác. Ví dụ:

| Trạng thái lịch đặt | Link có thể xuất hiện |
|---|---|
| PENDING | self, patient, slot, confirm, cancel |
| CONFIRMED | self, patient, slot, cancel |
| COMPLETED | self, patient, slot, receipt, feedback |
| CANCELLED | self, patient, slot |

Đây chỉ là ví dụ về hợp đồng của một ứng dụng. Tập link thực tế phụ thuộc vào nghiệp vụ và quyền. Nếu người dùng không có quyền hủy, server có thể không phát link cancel cho họ.

Việc link xuất hiện không thay thế xác thực và phân quyền. Client có thể gửi request thủ công, dùng một URL đã lưu hoặc có dữ liệu cũ. Server phải kiểm tra quyền và trạng thái tài nguyên ở mỗi request, rồi trả status code thích hợp nếu hành động không còn hợp lệ.

### 5.3. Affordance mô tả cách thực hiện hành động

Một link cơ bản cho biết client có thể đi đến đâu, nhưng có thể chưa mô tả đủ cách gửi request. Affordance bổ sung metadata về thao tác được hỗ trợ, chẳng hạn HTTP method, kiểu nội dung hoặc cấu trúc dữ liệu đầu vào.

Ví dụ, một affordance cập nhật thông tin bệnh nhân có thể mô tả rằng client gửi PATCH với một biểu diễn chứa trường `phoneNumber`. Các định dạng như HAL-FORMS có thể biểu diễn thông tin form để client khám phá cách gửi dữ liệu.

Affordance hữu ích khi client cần khám phá cả hành động và cấu trúc request. Nó không tự định nghĩa toàn bộ quy tắc nghiệp vụ, cũng không bảo đảm request sẽ thành công: server vẫn xác thực dữ liệu và kiểm tra quyền khi nhận request.

## 6. Spring HATEOAS hỗ trợ mức 3

Spring HATEOAS cung cấp các lớp và API để gắn link vào biểu diễn tài nguyên, tạo URI dựa trên mapping Spring MVC và xuất nội dung hypermedia như HAL. Một số kiểu thường gặp:

| Kiểu | Công dụng |
|---|---|
| RepresentationModel | Lớp cơ sở cho biểu diễn có link |
| EntityModel<T> | Bao một biểu diễn đơn lẻ cùng các link |
| CollectionModel<T> | Bao một tập hợp biểu diễn và link của collection |
| PagedModel<T> | Biểu diễn collection có thông tin phân trang |
| Link | Chứa href và relation |
| RepresentationModelAssembler<T, D> | Chuyển đối tượng miền hoặc DTO thành biểu diễn hypermedia |

Spring HATEOAS có thể được dùng cùng Spring MVC. Trong ứng dụng Spring Boot, dependency thường dùng là `spring-boot-starter-hateoas`; phiên bản nên được quản lý bằng Spring Boot dependency management của dự án.

### 6.1. Tạo biểu diễn và link bằng assembler

Giả sử ứng dụng có lớp miền `Booking`, `BookingService` với các phương thức truy vấn và nghiệp vụ, và DTO công khai:

~~~java
public record BookingRepresentation(
    UUID id,
    String status,
    OffsetDateTime appointmentTime
) {}
~~~

Assembler chuyển Booking thành EntityModel và thêm link dựa trên trạng thái:

~~~java
@Component
public class BookingModelAssembler
        implements RepresentationModelAssembler<Booking, EntityModel<BookingRepresentation>> {

    @Override
    public EntityModel<BookingRepresentation> toModel(Booking booking) {
        UUID id = booking.getId();

        EntityModel<BookingRepresentation> model = EntityModel.of(
            new BookingRepresentation(
                id,
                booking.getStatus().name(),
                booking.getAppointmentTime()
            ),
            linkTo(methodOn(BookingController.class).one(id)).withSelfRel()
        );

        model.add(
            linkTo(methodOn(BookingController.class).all())
                .withRel("bookings")
        );

        if (booking.canBeCancelled()) {
            model.add(
                linkTo(methodOn(BookingController.class).cancel(id))
                    .withRel("cancel")
            );
        }

        return model;
    }
}
~~~

Ở đây:

- `EntityModel` bao dữ liệu công khai và các link trong cùng biểu diễn.
- `linkTo(...)` lấy URI từ mapping Spring MVC.
- `methodOn(...)` mô tả phương thức controller và tham số để dựng URI; nó không gọi logic nghiệp vụ thực tế.
- Relation `cancel` chỉ được thêm khi booking cho phép hủy.

Controller có thể trả trực tiếp các mô hình hypermedia:

~~~java
@RestController
@RequestMapping("/bookings")
public class BookingController {

    private final BookingService service;
    private final BookingModelAssembler assembler;

    public BookingController(
            BookingService service,
            BookingModelAssembler assembler) {
        this.service = service;
        this.assembler = assembler;
    }

    @GetMapping("/{id}")
    public EntityModel<BookingRepresentation> one(@PathVariable UUID id) {
        return assembler.toModel(service.getRequired(id));
    }

    @GetMapping
    public CollectionModel<EntityModel<BookingRepresentation>> all() {
        return assembler.toCollectionModel(service.findAll())
            .add(linkTo(methodOn(BookingController.class).all()).withSelfRel());
    }

    @PostMapping("/{id}/cancellation")
    public ResponseEntity<Void> cancel(@PathVariable UUID id) {
        service.cancel(id);
        return ResponseEntity.noContent().build();
    }
}
~~~

Các import chính cho assembler và controller:

~~~java
import java.time.OffsetDateTime;
import java.util.UUID;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;
~~~

Các kiểu `Booking` và `BookingService` là thành phần miền của ứng dụng minh họa. Trong dự án thực tế, thay chúng bằng kiểu dữ liệu và phương thức service tương ứng. Không nên để assembler phụ thuộc vào chi tiết persistence nếu API có thể dùng DTO để kiểm soát dữ liệu được công bố.

Phương thức `cancel` vẫn phải kiểm tra trạng thái và quyền. Link cancel giúp client khám phá khả năng hiện tại, còn service chịu trách nhiệm quyết định request có được phép thực hiện hay không.

### 6.2. HAL là cách biểu diễn link phổ biến

HAL (Hypertext Application Language) quy ước:

- `_links` chứa các link của tài nguyên.
- `_embedded` chứa các tài nguyên được nhúng.
- Các key trong `_links` là relation; mỗi link thường có `href`.

Khi client gửi:

~~~http
GET /bookings/booking-99 HTTP/1.1
Accept: application/hal+json
~~~

Spring HATEOAS có thể serialize EntityModel thành HAL với media type `application/hal+json`. Ví dụ cấu trúc phản hồi:

~~~json
{
  "id": "booking-99",
  "status": "CONFIRMED",
  "appointmentTime": "2026-12-03T09:30:00+07:00",
  "_links": {
    "self": {
      "href": "https://api.example.com/bookings/booking-99"
    },
    "bookings": {
      "href": "https://api.example.com/bookings"
    },
    "cancel": {
      "href": "https://api.example.com/bookings/booking-99/cancellation"
    }
  }
}
~~~

Nếu booking không còn hủy được, assembler không thêm relation cancel và HAL không chứa link đó. Client cần xử lý trường hợp relation vắng mặt như một phần bình thường của hợp đồng.

## 7. Phân biệt các mức khi đánh giá một API

Khi đánh giá một API, hãy chọn một workflow cụ thể và theo dõi toàn bộ tương tác của client với server. Đừng chỉ đếm số endpoint hoặc kiểm tra API có dùng Spring HATEOAS hay không.

| Câu hỏi đánh giá | Mức được thể hiện |
|---|---|
| Nhiều hành động có bị dồn vào một endpoint và phân biệt bằng payload không? | Đặc trưng mức 0 |
| Các URI có định danh riêng bác sĩ, khung giờ, bệnh nhân và lịch đặt không? | Mức 1 |
| GET, POST, PUT, PATCH, DELETE, status code và header có được dùng đúng ngữ nghĩa không? | Mức 2 |
| Client có thể khám phá tài nguyên và hành động tiếp theo qua link relation trong biểu diễn không? | Mức 3 |

Một số tình huống dễ đánh giá nhầm:

- API có hàng trăm URI vẫn có thể dừng ở mức 1 nếu client phải gửi mọi lệnh bằng POST với action trong payload.
- API dùng GET, POST, DELETE đúng cách có thể ở mức 2 dù response là JSON thuần và không có hypermedia.
- API có trường `_links.self` nhưng client vẫn tự ghép URI cho mọi thao tác chưa thể hiện đầy đủ khả năng điều khiển của mức 3.
- Tài liệu OpenAPI mô tả endpoint và schema rất hữu ích, nhưng bản thân tài liệu tĩnh không thay thế hypermedia controls trong biểu diễn mà client nhận được khi chạy.
- Cài Spring HATEOAS hoặc trả EntityModel không bảo đảm API đạt mức 3 nếu các relation không giúp client khám phá workflow.

Một API có thể có endpoint ở các mức khác nhau. Ví dụ, một luồng mới đã cung cấp link điều hướng nhưng một endpoint cũ vẫn yêu cầu client tự dựng URI. Vì vậy, hãy đánh giá theo workflow quan trọng và xác định rõ phần nào đã đạt mức nào.

## 8. Lộ trình nâng cấp từ mức thấp lên mức cao

Không nhất thiết phải viết lại toàn bộ API cùng lúc. Có thể cải thiện theo các bước sau:

1. **Tách tài nguyên (mức 0 lên mức 1):** xác định các thực thể và khái niệm nghiệp vụ có định danh riêng; công bố URI ổn định cho từng tài nguyên.
2. **Chuẩn hóa HTTP (mức 1 lên mức 2):** chọn method theo ngữ nghĩa thao tác; dùng status code, Content-Type, Accept, Location, ETag và cache header phù hợp.
3. **Định nghĩa relation:** xác định các quan hệ như self, collection, next, cancel hoặc approve; viết rõ ý nghĩa để client có thể dựa vào chúng.
4. **Thêm link theo trạng thái:** dùng assembler để phát link phù hợp với trạng thái và quyền của người dùng.
5. **Bổ sung affordance khi cần:** mô tả method và dữ liệu đầu vào cho các thao tác mà client cần khám phá.
6. **Kiểm thử hợp đồng:** xác nhận link, relation, href, media type, trường hợp link vắng mặt và kết quả khi client gọi một hành động không còn hợp lệ.

Nên ưu tiên những workflow có nhiều bước hoặc thay đổi theo trạng thái, chẳng hạn phê duyệt đơn, đặt lịch, xử lý thanh toán hoặc theo dõi quy trình. Các luồng đọc đơn giản, ổn định có thể chưa cần affordance phức tạp.

## 9. Kiểm thử mức 3 bằng MockMvc

Ở mức 3, kiểm thử cần xác nhận nội dung hypermedia bên cạnh status code và dữ liệu. Ví dụ, với một booking đang CONFIRMED và còn được hủy, kiểm tra link cancel:

~~~java
@WebMvcTest(BookingController.class)
@Import(BookingModelAssembler.class)
class BookingControllerTest {

    @Autowired
    MockMvc mvc;

    @MockBean
    BookingService service;

    @Test
    void exposesCancelLinkWhenBookingCanBeCancelled() throws Exception {
        UUID id = UUID.fromString("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa");
        given(service.getRequired(id)).willReturn(confirmedBooking(id));

        mvc.perform(get("/bookings/{id}", id)
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
            .andExpect(jsonPath("$._links.self.href")
                .value(endsWith("/bookings/" + id)))
            .andExpect(jsonPath("$._links.cancel.href").exists());
    }
}
~~~

Với booking đã hoàn tất hoặc đã hủy, kiểm tra relation cancel vắng mặt:

~~~java
.andExpect(jsonPath("$._links.cancel").doesNotExist());
~~~

Các import thường dùng trong kiểm thử:

~~~java
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.endsWith;
import static org.mockito.BDDMockito.given;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
~~~

Trong dự án cụ thể, `confirmedBooking(id)` là fixture do nhóm kiểm thử định nghĩa. Ngoài hai trường hợp trên, cần kiểm tra:

- Collection có link self và các link điều hướng phù hợp.
- Client có thể theo link được trả về mà không phải ghép URI từ ID.
- Relation giữ nguyên ý nghĩa khi mapping nội bộ thay đổi.
- Content negotiation trả đúng media type được yêu cầu.
- Request hủy trực tiếp vẫn bị từ chối nếu booking không còn được hủy hoặc người dùng không có quyền, kể cả khi client giữ một href cũ.
- Link sinh ra sau reverse proxy hoặc gateway có host, scheme và context path công khai chính xác.

MockMvc xác minh controller, assembler và quá trình serialize trong ngữ cảnh ứng dụng kiểm thử. Với gateway, proxy hoặc cấu hình triển khai thực tế, nên có kiểm thử tích hợp để xác nhận URI công khai và hành vi điều hướng.

## 10. Khi nào nên nhắm đến mức 3?

Mức 3 có giá trị khi server cần mô tả workflow và các khả năng thay đổi theo trạng thái. Một số trường hợp phù hợp:

- API công khai có nhiều client do các nhóm khác nhau phát triển.
- Workflow gồm nhiều bước, có điều kiện chuyển trạng thái.
- Server cần thay đổi cấu trúc URI mà vẫn giữ quan hệ nghiệp vụ ổn định.
- Client cần khám phá hành động hiện có thay vì tự suy ra từ trạng thái và tài liệu tĩnh.
- Nhiều vai trò người dùng nhìn thấy các khả năng khác nhau trên cùng tài nguyên.

Mức 2 có thể là lựa chọn hợp lý cho API nội bộ có client được quản lý cùng nhau, workflow đơn giản và hợp đồng thay đổi có kiểm soát. Mức 3 bổ sung tính linh hoạt nhưng cũng yêu cầu thiết kế relation, hỗ trợ client đọc hypermedia, tài liệu hóa và kiểm thử hợp đồng cẩn thận. Mục tiêu là chọn mức phù hợp với cách API được sử dụng và tiến hóa, không phải đạt con số cao nhất bằng mọi giá.

## 11. Kết luận

Richardson Maturity Model mô tả bốn bước phát triển trong thiết kế API Web: mức 0 tập trung vào một điểm gọi kiểu RPC; mức 1 định danh tài nguyên bằng nhiều URI; mức 2 tận dụng HTTP method, status code và header; mức 3 đưa hypermedia controls vào biểu diễn để client khám phá tài nguyên và hành động tiếp theo.

Spring HATEOAS hỗ trợ trực tiếp cho mức 3 thông qua RepresentationModel, EntityModel, CollectionModel, Link, RepresentationModelAssembler và các định dạng như HAL. Khi relation được định nghĩa ổn định, link phản ánh đúng trạng thái và client thực sự điều hướng theo link, server có thể thay đổi cách tổ chức URI mà ít ảnh hưởng đến client. Việc kiểm tra quyền và quy tắc nghiệp vụ vẫn luôn thuộc trách nhiệm của server.

