# Thay đổi export ảnh hưởng binary compatibility

## 1. exports là một phần của hợp đồng module

Trong JPMS, chỉ khai báo `requires` chưa đủ để module khác sử dụng kiểu thuộc một module named. Module cung cấp còn phải export package chứa kiểu đó.

Ví dụ module thư viện công bố API:

~~~java
module com.acme.customer {
    exports com.acme.customer.api;
}
~~~

Một module tiêu thụ có thể đọc và sử dụng các kiểu public trong package đã export:

~~~java
module com.acme.application {
    requires com.acme.customer;
}
~~~

`exports` là ranh giới truy cập ở cấp package. Khi package được export, các kiểu và thành viên vẫn phải tuân theo quy tắc truy cập Java thông thường: một lớp top-level thường phải là `public`, và thành viên được sử dụng phải có mức truy cập phù hợp. Export package không biến lớp package-private hoặc thành viên private thành public.

Vì module tiêu thụ dựa vào chỉ thị export để biên dịch và chạy, việc thay đổi `exports` có thể ảnh hưởng trực tiếp đến chương trình đã biên dịch trước đó. Do đó, package đã công bố cần được xem như một phần của hợp đồng tương thích mà thư viện cam kết duy trì.

## 2. Ba thay đổi export cần phân biệt

Giả sử phiên bản đầu của thư viện có descriptor:

~~~java
module com.acme.customer {
    exports com.acme.customer.api;
}
~~~

Mọi named module đọc `com.acme.customer` đều có thể truy cập các kiểu public thuộc package `com.acme.customer.api`.

### Xóa exports

Phiên bản mới bỏ chỉ thị:

~~~java
module com.acme.customer {
    // Không còn exports com.acme.customer.api
}
~~~

Package trở thành nội bộ đối với các module khác. Một consumer đã biên dịch trước đó vẫn có thể chứa bytecode tham chiếu tới các lớp trong package này, nhưng khi JVM cần truy cập kiểu hoặc thành viên bị che khỏi module đó, việc kiểm tra quyền truy cập có thể thất bại với `IllegalAccessError`.

Consumer biên dịch lại với descriptor mới cũng sẽ bị từ chối khi import hoặc truy cập package không được export.

### Thu hẹp từ export công khai thành qualified export

Phiên bản đầu:

~~~java
module com.acme.customer {
    exports com.acme.customer.api;
}
~~~

Phiên bản sau:

~~~java
module com.acme.customer {
    exports com.acme.customer.api to com.acme.application;
}
~~~

Package giờ chỉ được export cho module `com.acme.application`. Các consumer khác trước đây đọc module customer và sử dụng package API sẽ mất quyền truy cập.

Đây là thay đổi có thể gây lỗi tương thích dù tên module, tên package, lớp public và chữ ký phương thức không đổi. Quyền truy cập đã thay đổi ở cấp module descriptor.

### Bỏ một module khỏi danh sách qualified export

Giả sử descriptor đang là:

~~~java
module com.acme.customer {
    exports com.acme.customer.spi
        to com.acme.application, com.acme.integration;
}
~~~

Nếu bản phát hành sau bỏ `com.acme.integration`:

~~~java
module com.acme.customer {
    exports com.acme.customer.spi
        to com.acme.application;
}
~~~

Consumer `com.acme.integration` không còn được phép truy cập package đó. Các consumer còn lại trong danh sách vẫn giữ quyền truy cập nếu những điều kiện khác không đổi.

## 3. Vì sao bytecode cũ có thể gặp IllegalAccessError?

Biên dịch Java và liên kết/chạy bytecode là hai thời điểm khác nhau:

1. Khi biên dịch consumer, compiler đọc module descriptor của thư viện và xác nhận package cần dùng được export cho consumer.
2. Compiler tạo bytecode chứa các tham chiếu tới kiểu, phương thức hoặc field của thư viện.
3. Khi chạy, JVM phân giải các tham chiếu và thực hiện kiểm tra truy cập theo module descriptor đang được nạp.
4. Nếu bản thư viện mới không còn export package cho module consumer, JVM có thể ném `IllegalAccessError` khi đường thực thi chạm tới tham chiếu bị cấm.

Ví dụ consumer đã được biên dịch với API:

~~~java
package com.acme.application;

import com.acme.customer.api.CustomerService;

public class Main {
    public static void main(String[] args) {
        CustomerService service = null;
        System.out.println(service);
    }
}
~~~

Consumer được biên dịch khi module customer còn export `com.acme.customer.api`. Sau đó ứng dụng thay JAR thư viện bằng phiên bản đã xóa export. Bytecode consumer không tự được biên dịch lại và vẫn chứa tham chiếu tới `CustomerService`. Khi JVM cần truy cập kiểu này, kiểm tra module access có thể thất bại với `IllegalAccessError`.

Lỗi có thể xuất hiện khi class hoặc member được liên kết hay sử dụng, không nhất thiết ngay tại thời điểm JVM khởi động. Vì vậy, chỉ chạy ứng dụng qua một đường code không dùng API đã bị thu hẹp chưa đủ chứng minh tương thích.

## 4. Phân biệt lỗi biên dịch và lỗi runtime

| Tình huống | Consumer biên dịch lại | Consumer bytecode cũ |
|---|---|---|
| Package vẫn export cho consumer | Có thể tiếp tục biên dịch nếu API còn tương thích | Có thể tiếp tục chạy nếu các điều kiện liên kết khác không đổi |
| Xóa unqualified export | Compiler báo package không được export/không hiển thị | Có thể gặp `IllegalAccessError` khi truy cập kiểu hoặc thành viên |
| Chuyển thành qualified export nhưng consumer không có trong danh sách | Compiler từ chối truy cập package | Có thể gặp `IllegalAccessError` |
| Xóa consumer khỏi qualified export | Compiler từ chối truy cập package | Có thể gặp `IllegalAccessError` |
| Thêm một qualified export cho consumer mới | Consumer mới có thể biên dịch | Consumer cũ khác không bị mất quyền chỉ vì export mới được thêm |

Thông báo compiler thường diễn đạt rằng package không được hiển thị hoặc module không export package cho module consumer. Thông báo runtime thường nêu rõ module nguồn, package và module đích không được phép truy cập.

Không nên gộp mọi lỗi sau khi thay đổi descriptor thành lỗi binary compatibility. Nếu một phương thức public bị xóa, kiểu bị đổi tên hoặc chữ ký thay đổi, consumer có thể gặp các lỗi liên kết khác như `NoSuchMethodError` hoặc `NoClassDefFoundError`. Nếu package không còn được export, vấn đề nằm ở quyền truy cập module và có thể dẫn tới `IllegalAccessError`.

## 5. Thêm export thường là thay đổi mở rộng, nhưng làm rộng API

Thêm một export:

~~~java
module com.acme.customer {
    exports com.acme.customer.api;
    exports com.acme.customer.events;
}
~~~

thường không làm mất quyền của consumer đang hoạt động. Các module khác có thể bắt đầu sử dụng package mới nếu chúng đọc module customer và các kiểu/member cần thiết là accessible.

Tuy vậy, export mới làm tăng bề mặt API công khai. Một khi consumer bắt đầu phụ thuộc vào package đó, việc thu hẹp hoặc xóa export trong phiên bản sau có thể trở thành thay đổi phá vỡ tương thích.

Trước khi export package mới, hãy xác nhận:

- Package có được hỗ trợ lâu dài không?
- Các kiểu public trong package đã ổn định chưa?
- Package có chứa implementation detail hoặc class chỉ phục vụ nội bộ không?
- Có thể dùng qualified export để chỉ công bố cho một module tích hợp cụ thể không?
- Việc công bố package có làm lộ thêm dependency trong API không?

Không nên export một package chỉ để làm một lỗi truy cập biến mất nếu package đó không thuộc hợp đồng mà thư viện muốn cung cấp.

## 6. Qualified exports và consumer classpath

Qualified export chỉ cấp quyền cho các module được nêu tên:

~~~java
module com.acme.customer {
    exports com.acme.customer.spi to com.acme.integration;
}
~~~

Điều này phù hợp với SPI nội bộ dành cho một module tích hợp đã biết. Nhưng cần nhớ:

- Module consumer phải có tên phù hợp với danh sách.
- Một consumer khác không được cấp quyền chỉ vì nó cũng khai báo `requires com.acme.customer`.
- Mã nằm trên classpath thuộc unnamed module, không có tên để liệt kê như một named consumer trong qualified export.
- Chuyển consumer từ module path sang classpath có thể thay đổi khả năng truy cập nếu package chỉ được export có điều kiện.

Nếu thư viện cần hỗ trợ cả consumer trên classpath lẫn nhiều named module, hãy cân nhắc liệu package nên là unqualified export hay nên có một API công khai khác. Đừng giả định qualified export sẽ tự áp dụng cho mọi consumer.

## 7. exports và opens là hai hợp đồng khác nhau

`exports` kiểm soát truy cập thông thường tới các kiểu public của package. `opens` cho phép reflection sâu trên package ở runtime.

Ví dụ:

~~~java
module com.acme.customer {
    exports com.acme.customer.api;
    opens com.acme.customer.model to com.acme.persistence;
}
~~~

Nếu xóa:

~~~java
exports com.acme.customer.api;
~~~

thì consumer Java thông thường có thể mất quyền truy cập API. Nếu xóa:

~~~java
opens com.acme.customer.model to com.acme.persistence;
~~~

thì framework persistence có thể gặp lỗi reflection như `InaccessibleObjectException`, dù mã consumer vẫn biên dịch và package model không được dùng trực tiếp trong source code.

Ngược lại, giữ `opens` không thay thế `exports`. Một package chỉ được mở cho reflection không vì thế trở thành API có thể import và gọi trực tiếp từ module khác.

Khi thay đổi descriptor, kiểm tra cả hai loại quyền riêng biệt: consumer source/binary đối với exports và framework runtime đối với opens.

## 8. Cách kiểm thử tác động của thay đổi export

Một lần build thành công của thư viện chỉ chứng minh source của chính thư viện biên dịch được. Để đánh giá tác động với consumer, hãy kiểm tra trên cả consumer mới và bytecode cũ.

### Bước 1: Giữ lại consumer đã biên dịch với descriptor cũ

Biên dịch một module consumer khi package còn được export:

~~~java
module com.acme.application {
    requires com.acme.customer;
}
~~~

Consumer gọi một API thuộc package được export. Lưu lại artifact consumer đã biên dịch để thử với bản thư viện mới.

### Bước 2: Build thư viện với descriptor mới

Tạo JAR phát hành ứng viên, trong đó export đã được xóa hoặc thu hẹp theo thay đổi đang đánh giá.

### Bước 3: Chạy bytecode cũ với JAR mới

Đặt JAR thư viện mới và bytecode consumer cũ vào module path. Chạy đúng đường code truy cập package bị thay đổi. Ghi nhận lỗi liên kết hoặc lỗi quyền truy cập, nếu có.

### Bước 4: Biên dịch lại consumer

Dùng module path mới để biên dịch lại consumer. Nếu package không còn được export cho module đó, compiler sẽ phát hiện vấn đề trước runtime.

### Bước 5: Thử tất cả qualified consumer và classpath consumer được hỗ trợ

Nếu descriptor có `exports ... to A, B`, thử riêng A và B. Nếu thư viện cam kết hỗ trợ mã classpath, kiểm tra cả unnamed module vì nó không có tên trong danh sách qualified export.

### Bước 6: Kiểm tra reflection và service độc lập

Chạy framework thực tế để kiểm tra `opens`; kiểm tra `ServiceLoader` nếu module có `uses` hoặc `provides`. Một bài thử truy cập API thông thường không thay thế được các bài thử này.

## 9. Công cụ hỗ trợ kiểm tra artifact

Sau khi build JAR mới:

~~~bash
jar --describe-module --file build/libs/customer-module.jar
jar --list --file build/libs/customer-module.jar
~~~

Hai lệnh này giúp xác nhận descriptor và package được đóng gói trong artifact thực tế.

Có thể kiểm tra module descriptor so với dependency được phát hiện:

~~~bash
jdeps --check com.acme.customer --module-path mods
~~~

Và kiểm tra module configuration khi chạy:

~~~bash
java --show-module-resolution \
  --module-path mods \
  -m com.acme.application/com.acme.application.Main
~~~

Các công cụ trên giúp xác nhận tên module, descriptor và quan hệ dependency. Chúng không thay thế việc chạy consumer đã biên dịch trước đó với JAR mới; bài thử consumer mới và cũ mới trực tiếp phát hiện ảnh hưởng tương thích của export.

Trong giai đoạn chẩn đoán, có thể dùng `--add-exports` để kiểm chứng giả thuyết về quyền truy cập:

~~~bash
java --add-exports com.acme.customer/com.acme.customer.api=com.acme.application \
  --module-path mods \
  -m com.acme.application/com.acme.application.Main
~~~

Tùy chọn này bổ sung quyền export ở runtime cho lần chạy đó. Nó hữu ích để xác định nguyên nhân hoặc hỗ trợ migration có kiểm soát, nhưng không sửa descriptor trong JAR và không nên được xem là giải pháp phát hành lâu dài thay cho hợp đồng module đúng.

## 10. Chính sách tương thích khi phát hành

Nếu package đã được export công khai và được tài liệu hóa là API hỗ trợ, hãy xem việc xóa export hoặc thu hẹp danh sách consumer là thay đổi phá vỡ tương thích.

Một quy trình phát hành có thể áp dụng:

- **Bản vá (patch)**: giữ nguyên các export công khai và các consumer đã được hỗ trợ; chỉ sửa lỗi nội bộ hoặc bổ sung quyền tương thích có kiểm soát.
- **Bản minor**: có thể bổ sung package export hoặc qualified export mới khi API mới đã ổn định và việc mở rộng phù hợp chính sách tương thích.
- **Bản major**: thực hiện thay đổi có chủ đích như xóa export, đổi tên package/module hoặc thu hẹp qualified export đã công bố; kèm migration note và hướng dẫn thay thế.

Đây là chính sách phiên bản ở cấp thư viện, không phải quy tắc bắt buộc của JPMS. Nhóm phát triển cần xác định rõ package nào là API được hỗ trợ, package nào chỉ là chi tiết nội bộ và module consumer nào được bảo đảm.

Nếu cần ngừng một package API, có thể phát hành giai đoạn chuyển tiếp: công bố API thay thế, đánh dấu API cũ deprecated, hướng dẫn consumer chuyển đổi, đo lường hoặc kiểm tra các consumer đã biết, rồi mới thu hẹp export trong major release.

## 11. Checklist trước khi thay đổi exports

- [ ] Liệt kê mọi package đang được export trong descriptor hiện hành.
- [ ] Xác định các module consumer đã biết đang sử dụng từng package.
- [ ] Kiểm tra package là API công khai, SPI có giới hạn hay implementation detail.
- [ ] Đánh giá riêng thay đổi unqualified export và qualified export.
- [ ] Xác định consumer nào sẽ mất quyền truy cập nếu xóa hoặc thu hẹp export.
- [ ] Biên dịch lại consumer với descriptor mới để phát hiện lỗi source.
- [ ] Chạy bytecode consumer cũ với JAR mới để phát hiện lỗi runtime như `IllegalAccessError`.
- [ ] Kiểm tra `opens` riêng cho framework reflection.
- [ ] Xác nhận JAR cuối cùng chứa đúng `module-info.class` và descriptor dự kiến.
- [ ] Cập nhật phiên bản, migration note và tài liệu API theo mức ảnh hưởng.

## Kết luận

Thay đổi `exports` là thay đổi quyền truy cập ở cấp module. Xóa một export, chuyển export công khai thành qualified export hoặc bỏ một consumer khỏi danh sách cho phép có thể khiến source không biên dịch lại được và bytecode cũ gặp `IllegalAccessError` khi JVM kiểm tra quyền truy cập.

Trước khi phát hành, hãy xem package đã export là một phần của hợp đồng tương thích, kiểm tra cả consumer mới lẫn bytecode cũ, và xác nhận descriptor trên chính JAR cuối cùng. Cách kiểm tra này giúp thay đổi API module có chủ đích, có phiên bản phù hợp và có hướng dẫn migration rõ ràng.
