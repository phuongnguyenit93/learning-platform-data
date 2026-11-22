# Rà soát package nào thực sự cần export

Trong Java Platform Module System (JPMS), chỉ thị `exports` công bố package của một module cho các module khác. Mỗi package được export trở thành một phần bề mặt API mà module đang cung cấp. Vì vậy, quyết định export ảnh hưởng trực tiếp đến mức độ phụ thuộc giữa các module, khả năng thay đổi implementation và phạm vi tương thích mà thư viện phải duy trì.

Một module có thể chứa nhiều package public, nhưng điều đó không có nghĩa tất cả đều nên được export. Việc rà soát cần bắt đầu từ câu hỏi: **module bên ngoài có thực sự cần sử dụng package này như một phần hợp đồng của module hay không?**

## Mục tiêu

Sau bài học, bạn có thể:

- Kiểm kê package của một named module và phân loại theo vai trò.
- Xác định package nào cần trở thành API công khai.
- Phân biệt package API, package implementation và package chỉ phục vụ framework.
- Quyết định giữa không export, export không giới hạn và qualified export.
- Nhận biết trường hợp cần `opens` hoặc Service Provider thay vì export package.
- Rà soát module descriptor và kiểm tra tác động của việc thu hẹp API.

## 1. exports công bố điều gì?

Chỉ thị `exports` được khai báo trong `module-info.java`:

~~~java
module com.acme.orders {
    exports com.acme.orders.api;
}
~~~

Khai báo này công bố package `com.acme.orders.api` cho các module đọc được `com.acme.orders`.

Một module sử dụng API vẫn cần khai báo dependency:

~~~java
module com.acme.application {
    requires com.acme.orders;
}
~~~

Hai điều kiện phối hợp với nhau:

- `requires` xác định module sử dụng đọc module cung cấp.
- `exports` xác định package nào của module cung cấp được công bố cho module khác.

Export package không biến mọi kiểu hoặc thành viên thành public. Quy tắc truy cập của Java vẫn áp dụng. Một class cấp cao nhất cần có mức truy cập phù hợp; các constructor, method và field vẫn chịu sự chi phối của `public`, `protected`, package-private và `private`.

### 1.1. Export theo package, không theo class

JPMS export cả package. Không có cú pháp kiểu:

~~~java
exports com.acme.orders.api.OrderService;
~~~

Thay vào đó, module công bố package:

~~~java
exports com.acme.orders.api;
~~~

Các package con là package riêng. Ví dụ:

- `com.acme.orders.api`
- `com.acme.orders.api.dto`
- `com.acme.orders.internal`

Export package `com.acme.orders.api` không tự động export `com.acme.orders.api.dto` hoặc `com.acme.orders.internal`. Nếu muốn công bố package con, phải khai báo riêng.

Do đó, cách tổ chức package có ảnh hưởng trực tiếp đến độ rộng của API module. Đặt class nội bộ cùng package với API có thể khiến package đó phải export chỉ để một số class được truy cập. Tách API và implementation thành package riêng thường giúp kiểm soát ranh giới tốt hơn.

## 2. Bắt đầu bằng kiểm kê package

Trước khi sửa module descriptor, hãy liệt kê package thực tế trong module. Với mỗi package, ghi lại:

- Tên package.
- Những class, interface, enum và annotation quan trọng.
- Module nào đang import hoặc sử dụng kiểu trong package.
- Package có xuất hiện trong chữ ký API public của module khác không.
- Framework hoặc công cụ nào cần truy cập package lúc chạy.
- Package chứa API ổn định hay chi tiết triển khai có thể thay đổi.

Có thể dùng cấu trúc bảng sau làm phiếu rà soát:

| Package | Người sử dụng | Vai trò | Quyết định ban đầu |
|---|---|---|---|
| `com.acme.orders.api` | App, integration | API công khai | Export |
| `com.acme.orders.dto` | App, integration | Kiểu dữ liệu trao đổi | Export nếu là hợp đồng API |
| `com.acme.orders.internal` | Chỉ module orders | Implementation | Không export |
| `com.acme.orders.persistence` | ORM qua reflection | Persistence nội bộ | Xem xét opens |
| `com.acme.orders.bootstrap` | Chỉ mã khởi tạo nội bộ | Implementation | Không export |

Bảng trên chỉ là ví dụ phân loại. Quyết định cuối cùng phải dựa trên cấu trúc và cách sử dụng thực tế của module đang rà soát.

## 3. Tiêu chí quyết định package có cần export không

### 3.1. Package chứa API mà module khác gọi trực tiếp

Đây là ứng viên rõ ràng nhất để export.

Ví dụ package `com.acme.payment.api` cung cấp service mà ứng dụng bên ngoài cần gọi:

~~~java
package com.acme.payment.api;

public interface PaymentService {
    PaymentResult pay(PaymentRequest request);
}
~~~

Nếu module khác cần import `PaymentService`, `PaymentResult` và `PaymentRequest`, package chứa các kiểu đó phải được export cho module sử dụng.

~~~java
module com.acme.payment {
    exports com.acme.payment.api;
}
~~~

Một API công khai nên có mục đích rõ ràng, kiểu dữ liệu ổn định và hợp đồng mà module cung cấp sẵn sàng duy trì.

### 3.2. Package chỉ chứa implementation nội bộ

Các package chứa helper, adapter, repository implementation, thuật toán nội bộ hoặc class phục vụ wiring thường không cần export nếu module khác không truy cập trực tiếp chúng.

Ví dụ:

~~~text
com.acme.payment
├── api
│   ├── PaymentService.java
│   └── PaymentResult.java
├── internal
│   ├── DefaultPaymentService.java
│   └── PaymentValidator.java
└── persistence
    └── JpaPaymentRepository.java
~~~

Module descriptor có thể chỉ công bố API:

~~~java
module com.acme.payment {
    exports com.acme.payment.api;
}
~~~

Các class trong package `internal` và `persistence` vẫn được sử dụng bên trong module. Module khác không thể truy cập chúng qua API Java thông thường nếu package không được export.

Giữ implementation trong package không export giúp module có thể đổi class, cấu trúc và thuật toán nội bộ mà ít ảnh hưởng đến client.

### 3.3. Package có kiểu public nhưng không có client bên ngoài

Từ khóa `public` trên một class không tự động khiến package cần export.

Ví dụ:

~~~java
package com.acme.payment.internal;

public class PaymentRetryPolicy {
    public boolean shouldRetry(int attempt) {
        return attempt < 3;
    }
}
~~~

Nếu chỉ các class khác trong module payment sử dụng `PaymentRetryPolicy`, không có lý do phải export package `com.acme.payment.internal`.

Quyết định export dựa trên ranh giới module và hợp đồng cần công bố, không dựa riêng vào việc class được khai báo public.

### 3.4. Package chỉ được framework truy cập bằng reflection

Một số framework cần đọc annotation, tạo object, truy cập field hoặc gọi constructor bằng reflection. Trường hợp này cần xác định framework đang cần truy cập public API hay deep reflection.

- Nếu framework sử dụng API public theo cách thông thường, package có thể cần export.
- Nếu framework cần deep reflection vào thành viên không public, package có thể cần mở bằng `opens`.
- Nếu framework chỉ cần một package cho module framework cụ thể, ưu tiên giới hạn đối tượng được cấp quyền.

Ví dụ:

~~~java
module com.acme.payment {
    exports com.acme.payment.api;
    opens com.acme.payment.persistence to com.acme.orm;
}
~~~

Package API được export cho việc sử dụng thông thường. Package persistence được mở cho module ORM thực hiện reflection lúc chạy.

Không nên export toàn bộ package nội bộ chỉ vì một framework cần truy cập sâu vào một số thành viên.

### 3.5. Package triển khai Service Provider

Với cơ chế `ServiceLoader`, module cung cấp có thể khai báo provider trong module descriptor:

~~~java
module com.acme.payment.provider {
    requires com.acme.payment.api;

    provides com.acme.payment.api.PaymentService
        with com.acme.payment.provider.internal.DefaultPaymentService;
}
~~~

Module tiêu thụ khai báo:

~~~java
module com.acme.application {
    requires com.acme.payment.api;
    uses com.acme.payment.api.PaymentService;
}
~~~

Package chứa interface service cần được công bố cho client. Package triển khai provider thường không cần export chỉ để `ServiceLoader` tìm và khởi tạo provider đã khai báo bằng `provides ... with ...`.

Đây là ví dụ cho thấy một package có thể được sử dụng gián tiếp qua cơ chế module mà không cần trở thành API package công khai.

## 4. Ba lựa chọn khi rà soát

Sau khi xác định mục đích của package, chọn một trong các hướng sau.

### 4.1. Không export

Dùng khi package chỉ phục vụ implementation nội bộ và không cần được module khác truy cập trực tiếp.

~~~java
module com.acme.orders {
    exports com.acme.orders.api;
}
~~~

Package `com.acme.orders.internal` không xuất hiện trong descriptor nên vẫn là nội bộ của module.

### 4.2. Export không giới hạn

Dùng khi package là API mà các module đọc module hiện tại có thể sử dụng:

~~~java
module com.acme.orders {
    exports com.acme.orders.api;
}
~~~

Mọi module đọc `com.acme.orders` đều được phép truy cập API public đủ điều kiện trong package đã export.

Đây là cam kết API rộng hơn qualified export. Hãy cân nhắc tính ổn định và nhu cầu của các client trước khi công bố.

### 4.3. Qualified export

Dùng khi package cần được công bố cho một số module có tên cụ thể:

~~~java
module com.acme.orders {
    exports com.acme.orders.api;
    exports com.acme.orders.spi to com.acme.plugin;
}
~~~

Trong ví dụ này:

- Package `com.acme.orders.api` được công bố cho mọi module đọc `com.acme.orders`.
- Package `com.acme.orders.spi` chỉ được công bố cho module `com.acme.plugin` qua khai báo này.

Module đích vẫn cần đọc module cung cấp, ví dụ:

~~~java
module com.acme.plugin {
    requires com.acme.orders;
}
~~~

Qualified export hữu ích cho SPI, integration nội bộ giữa một số module hoặc API chỉ dành cho thành phần được kiểm soát. Nó không thay thế `requires` và không mở package cho deep reflection.

## 5. Quy trình rà soát package theo từng bước

Có thể áp dụng quy trình sau cho một module đang có nhiều package hoặc đã export rộng từ trước.

### Bước 1: Lập danh sách package

Liệt kê package có mã nguồn trong module. Nhóm theo vai trò:

- API công khai.
- DTO/model trao đổi giữa module.
- SPI hoặc extension point.
- Implementation.
- Persistence và adapter.
- Bootstrap, configuration và helper.
- Package phục vụ framework hoặc reflection.

Không mặc định package có tên `api` chắc chắn là API ổn định; cần kiểm tra nội dung và client thực tế.

### Bước 2: Tìm module tiêu thụ

Tìm các module khác có:

- `requires` module đang rà soát.
- Câu lệnh import kiểu thuộc package đang xét.
- Chữ ký public sử dụng kiểu thuộc package đó.
- Cấu hình ServiceLoader hoặc framework cần package tương ứng.

Một package chỉ được dùng nội bộ trong cùng module thường không cần export.

### Bước 3: Xác định loại truy cập

Với từng client, xác định cách package được dùng:

- Import và gọi public API.
- Kế thừa hoặc triển khai interface public.
- Truyền kiểu qua tham số, kiểu trả về hoặc generic.
- Được tìm qua `ServiceLoader`.
- Được framework truy cập bằng reflection.
- Chỉ được gọi từ mã nội bộ của module.

Mỗi cách sử dụng có thể dẫn tới quyết định khác nhau. Ví dụ, API public thường cần export; deep reflection thường cần opens; provider đã khai báo trong descriptor thường không cần export package triển khai.

### Bước 4: Chọn phạm vi công bố

Đối với package cần export, hỏi tiếp:

- Mọi module đọc module này có cần truy cập không?
- Chỉ một module hoặc nhóm module tích hợp cần truy cập?
- Package có chứa class nội bộ không liên quan đến client không?
- Có thể tách API ra package riêng để giảm bề mặt công khai không?

Chọn export không giới hạn, qualified export hoặc tách package theo nhu cầu thực tế.

### Bước 5: Cập nhật module-info.java

Ví dụ trước khi rà soát:

~~~java
module com.acme.orders {
    exports com.acme.orders.api;
    exports com.acme.orders.internal;
    exports com.acme.orders.persistence;
    exports com.acme.orders.bootstrap;
}
~~~

Sau khi kiểm tra client, giả sử chỉ API cần được công bố, còn persistence cần reflection từ ORM:

~~~java
module com.acme.orders {
    exports com.acme.orders.api;
    opens com.acme.orders.persistence to com.acme.orm;
}
~~~

Package `internal` và `bootstrap` không còn export. Package persistence được mở đúng cho ORM nếu yêu cầu deep reflection đã được xác nhận.

Đây chỉ là ví dụ minh họa. Không xóa export đang được client sử dụng trước khi xác định và xử lý tác động của thay đổi.

### Bước 6: Kiểm tra client và runtime

Sau khi chỉnh descriptor:

1. Biên dịch module cung cấp.
2. Biên dịch từng module client sử dụng API.
3. Chạy các luồng tích hợp có liên quan.
4. Kiểm tra framework cần reflection.
5. Kiểm tra ServiceLoader nếu module có provider.
6. Tìm các lỗi truy cập package hoặc kiểu không còn được công bố.

Nếu một client thất bại vì package không được export, cần xác định client đó có đang sử dụng API được hỗ trợ hay đang phụ thuộc vào implementation. Kết quả rà soát phải phản ánh hợp đồng thực tế của module.

## 6. Công cụ hỗ trợ kiểm kê và phân tích

### 6.1. Tìm package trong mã nguồn

Có thể dùng công cụ tìm kiếm trong IDE hoặc dòng lệnh để liệt kê các khai báo package và vị trí import. Ví dụ với ripgrep:

~~~bash
rg "^package " src
rg "^import com\.acme\.orders" ../
~~~

Điều chỉnh thư mục tìm kiếm theo cấu trúc repository. Kết quả tìm kiếm giúp tìm các tham chiếu trong source code, nhưng không tự phát hiện mọi trường hợp reflection, cấu hình framework hoặc client được biên dịch riêng.

### 6.2. Dùng jdeps

Công cụ `jdeps` trong JDK giúp phân tích dependency ở cấp package và module.

Liệt kê dependency module:

~~~bash
jdeps --module-path libs --list-deps app.jar
~~~

Giới hạn phân tích vào API:

~~~bash
jdeps --api-only --module-path libs app.jar
~~~

Kiểm tra module descriptor và dependency:

~~~bash
jdeps --module-path libs --check com.acme.orders
~~~

Các kết quả của `jdeps` hỗ trợ xác định dependency và kiểu xuất hiện trong API. Chúng không thay thế việc rà soát yêu cầu nghiệp vụ, reflection, cấu hình runtime hoặc hợp đồng tích hợp. Hãy kết hợp phân tích tĩnh với việc kiểm tra client thực tế.

### 6.3. Kiểm tra descriptor và module graph

Có thể xem module descriptor của một JAR:

~~~bash
jar --describe-module --file libs/orders.jar
~~~

Khi chạy ứng dụng, có thể xem module resolution:

~~~bash
java --show-module-resolution --module-path out -m com.acme.app/com.acme.app.Main
~~~

Các lệnh này giúp kiểm tra tên module, requires và những module đã được giải quyết trong cấu hình chạy.

## 7. Cẩn trọng khi thu hẹp export

Loại bỏ một dòng export có thể làm mã nguồn của client hiện tại không biên dịch được. Nếu client đang import class thuộc package đó, lỗi có thể xuất hiện ngay ở compile time.

Một package từng được export cũng có thể đã trở thành dependency không chính thức của hệ thống. Trước khi thu hẹp:

- Xác định tất cả module tiêu thụ đã biết.
- Kiểm tra mã nguồn và cấu hình tích hợp bên ngoài repository nếu có.
- Xác định package có phải hợp đồng công khai được hỗ trợ không.
- Nếu cần, chuyển API cần giữ lại sang package công khai riêng.
- Cập nhật client trước hoặc cùng đợt thay đổi.
- Chạy lại biên dịch và kiểm thử tích hợp.

Không nên xóa export chỉ vì package có tên `internal` hoặc không xuất hiện trong một lần tìm kiếm. Cần xác minh các cách sử dụng hợp lệ và phạm vi client mà hệ thống phải hỗ trợ.

Ngược lại, export quá rộng cũng tạo rủi ro: client có thể bắt đầu phụ thuộc vào class nội bộ, khiến module khó thay đổi implementation và khó duy trì tương thích.

## 8. Checklist cho mỗi package

Dùng checklist này khi ghi nhận quyết định:

- [ ] Package đã được xác định đúng trong module.
- [ ] Đã tìm các module client và cách chúng sử dụng package.
- [ ] Đã phân biệt API public với implementation nội bộ.
- [ ] Đã xác định package có xuất hiện trong chữ ký API của module khác không.
- [ ] Đã kiểm tra nhu cầu reflection và ServiceLoader.
- [ ] Đã chọn không export, export không giới hạn, qualified export hoặc opens.
- [ ] Nếu thu hẹp export, đã đánh giá tác động tới client.
- [ ] Đã biên dịch và chạy các module liên quan.
- [ ] Module descriptor phản ánh đúng hợp đồng cần công bố.

Một bảng quyết định cuối cùng có thể được lưu cùng tài liệu thiết kế:

| Package | Client cần truy cập | Quyết định | Lý do |
|---|---|---|---|
| `com.acme.orders.api` | App, integration | Export | API public |
| `com.acme.orders.spi` | Module plugin cụ thể | Qualified export | Extension contract |
| `com.acme.orders.internal` | Không có client bên ngoài | Không export | Implementation |
| `com.acme.orders.persistence` | ORM qua deep reflection | Opens cho ORM | Truy cập runtime |
| `com.acme.orders.provider.internal` | ServiceLoader | Không export | Provider khai báo bằng provides |

## 9. Tự kiểm tra

**Tình huống 1:** Module A khai báo `requires B;`. Module nào là module phụ thuộc?

**Trả lời:** A là module phụ thuộc; B là module được yêu cầu. Quan hệ đọc trực tiếp đi từ A tới B.

**Tình huống 2:** A yêu cầu B, B yêu cầu C bằng `requires C;`. A có tự động đọc C không?

**Trả lời:** Không. `requires` thường không truyền khả năng đọc tới module phụ thuộc gián tiếp. A cần khai báo dependency trực tiếp vào C hoặc B dùng `requires transitive C;`.

**Tình huống 3:** Vì sao một module có mặt trên module path nhưng vẫn không được app sử dụng?

**Trả lời:** Module path chỉ cung cấp vị trí để Java tìm module. App còn phải khai báo quan hệ `requires` phù hợp; package được sử dụng cũng phải được export và kiểu phải đáp ứng quy tắc truy cập.

**Tình huống 4:** Một module dùng dependency chỉ trong compile time. Có thể chọn modifier nào?

**Trả lời:** Có thể dùng `requires static` nếu dependency không bắt buộc lúc chạy và code runtime không phụ thuộc sự hiện diện của class đó.

**Tình huống 5:** Khi nào nên dùng `requires transitive`?

**Trả lời:** Khi module muốn module đọc nó cũng đọc dependency, thường vì kiểu của dependency xuất hiện trong API public mà client cần sử dụng.

**Tình huống 6:** Một package không export nhưng được khai báo trong `provides ... with ...`. Có nhất thiết phải export package provider không?

**Trả lời:** Không. Provider được khai báo trong module descriptor để ServiceLoader tìm thấy; package triển khai provider thường có thể giữ nội bộ. Package chứa service interface vẫn cần được công bố cho module tiêu thụ.

Khi rà soát một dòng `requires`, hãy xác định module đang khai báo, module được yêu cầu, hướng cạnh phụ thuộc, modifier và cách dependency được sử dụng trong API. Sau đó kiểm tra module path, package export và client để bảo đảm đồ thị module phản ánh đúng kiến trúc mong muốn.