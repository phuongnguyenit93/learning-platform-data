# Giới hạn việc mở package thay vì open module toàn bộ

Java Platform Module System (JPMS) đóng gói package theo ranh giới module. Khi một framework cần dùng reflection sâu để đọc hoặc thay đổi thành viên private, module sở hữu package phải cho phép truy cập phù hợp. Chỉ thị **opens** và khai báo **open module** đều hỗ trợ reflection, nhưng phạm vi mở rất khác nhau.

Trong phần lớn ứng dụng, nên mở đúng package mà framework cần sử dụng. Mở toàn bộ module chỉ hợp lý khi chủ đích thiết kế thực sự yêu cầu mọi package đều có thể được truy cập sâu bằng reflection.

## 1. Vì sao reflection cần mở package?

Reflection cho phép chương trình khám phá class, method, field và constructor khi chạy. Một số framework dùng reflection để:

- Ánh xạ field của entity vào cột cơ sở dữ liệu.
- Đọc và ghi thuộc tính khi serialize hoặc deserialize JSON.
- Tạo object thông qua constructor.
- Tiêm dependency vào field hoặc constructor.
- Khám phá annotation và metadata của class.

Nếu framework chỉ gọi API public đã được export, thông thường nó không cần quyền mở package cho deep reflection. Nhưng khi framework cần truy cập thành viên private hoặc package không được export, quy tắc đóng gói của JPMS có thể chặn thao tác.

Ví dụ một entity:

~~~java
package com.example.orders.model;

public class Order {
    private String orderCode;

    private Order() {
    }

    public String getOrderCode() {
        return orderCode;
    }
}
~~~

Framework ORM có thể cần gọi constructor private hoặc truy cập field **orderCode** để tạo và nạp entity. Việc class là public hoặc có getter không đảm bảo framework được phép dùng reflection sâu vào mọi thành viên của package.

Khi quyền truy cập bị chặn, các thao tác như **setAccessible(true)** có thể phát sinh **InaccessibleObjectException**. Với **trySetAccessible()**, kết quả có thể là **false** nếu quyền truy cập không thể được mở. Khi đó cần xem package thuộc module nào và module đó đã mở package cho framework hay chưa.

## 2. Mở đúng package bằng opens

Chỉ thị **opens** đặt trong **module-info.java** cho phép reflection sâu vào một package ở runtime.

Ví dụ module quản lý đơn hàng chỉ mở package model:

~~~java
module com.example.orders {
    exports com.example.orders.api;

    opens com.example.orders.model;
}
~~~

Trong ví dụ này:

- Package **com.example.orders.api** được export để module khác sử dụng API public.
- Package **com.example.orders.model** được mở cho deep reflection ở runtime.
- Các package còn lại tiếp tục được đóng gói theo module descriptor.

Chỉ thị **opens** không làm package trở thành API Java công khai để module khác import và sử dụng trực tiếp. Nó giải quyết quyền truy cập bằng reflection, đặc biệt là reflection vào thành viên không public. Muốn module khác truy cập API thông thường, vẫn cần **exports** phù hợp và quan hệ đọc module như **requires**.

Một điểm quan trọng: **opens** áp dụng cho toàn bộ package, không chọn riêng một class hoặc một field. Vì vậy, nên gom các class cần framework xử lý vào package phù hợp, tránh đặt quá nhiều implementation nội bộ không liên quan vào cùng package được mở.

## 3. Qualified opens: chỉ mở cho framework cần dùng

Nếu biết chính xác module framework cần reflection, hãy dùng **qualified opens** để giới hạn module đích:

~~~java
module com.example.orders {
    exports com.example.orders.api;

    opens com.example.orders.model to com.example.orm;
}
~~~

Chỉ module **com.example.orm** được quyền reflection sâu vào package model theo directive này. Những module khác không nhận được quyền mở package đó chỉ vì chúng đọc module orders.

Có thể mở một package cho nhiều module đích:

~~~java
module com.example.orders {
    opens com.example.orders.model to
        com.example.orm,
        com.example.json;
}
~~~

Cách này phù hợp khi ứng dụng dùng nhiều framework độc lập, ví dụ ORM và JSON mapper. Mỗi framework chỉ được cấp quyền trên package mà nó thực sự cần.

Tên module đích phải là tên module JPMS mà framework công bố. Tên artifact trên Maven hoặc tên dependency trong Gradle không nhất thiết trùng với module name. Có thể kiểm tra tên module của JAR bằng lệnh **jar --describe-module** trước khi khai báo qualified opens.

## 4. open module mở rộng phạm vi ra sao?

JPMS cũng hỗ trợ khai báo **open module**:

~~~java
open module com.example.orders {
    exports com.example.orders.api;
}
~~~

Khai báo này mở tất cả package của module cho deep reflection ở runtime. Các module khác có thể thực hiện reflection sâu vào package trong module orders theo cơ chế mở của JPMS.

Tuy nhiên, **open module không đồng nghĩa với export toàn bộ package**:

- Các package không được export vẫn không trở thành API Java công khai thông thường.
- Module khác không thể tùy ý import class từ package không export chỉ vì module được khai báo open.
- Quyền được mở rộng ở đây là quyền truy cập sâu bằng reflection tại runtime.

Một open module không cần liệt kê từng directive **opens**. Trên thực tế, không đặt các directive **opens** riêng trong một khai báo open module; modifier open đã mở toàn bộ package. Nếu muốn giới hạn package hoặc module đích, hãy dùng một module bình thường với các directive **opens** cụ thể.

So sánh:

| Cách khai báo | Phạm vi reflection sâu | Có export API không? |
|---|---|---|
| Không có opens | Không mở package theo directive | Chỉ package có exports |
| opens package | Mở một package cho mọi module | Không tự export |
| opens package to module | Mở một package cho module được chọn | Không tự export |
| open module | Mở mọi package cho reflection sâu | Không tự export |

## 5. Vì sao không nên open module toàn bộ một cách mặc định?

Mở toàn bộ module có thể giúp framework hoạt động nhanh trong giai đoạn đầu, nhưng làm suy yếu ranh giới đóng gói mà module được thiết kế để bảo vệ.

**Tăng bề mặt truy cập nội bộ**

Khi mọi package đều mở, nhiều module có thể reflection sâu vào field, constructor và method private của implementation. Những chi tiết vốn được module sở hữu kiểm soát có thể trở thành điểm phụ thuộc ngầm.

**Tăng coupling với framework**

Framework có thể bắt đầu dựa vào cấu trúc field, constructor hoặc tên thuộc tính nội bộ. Khi implementation thay đổi, code bên ngoài có thể bị ảnh hưởng dù API public vẫn giữ nguyên.

**Khó thay đổi implementation**

Nếu nhiều framework có thể truy cập sâu vào mọi package, việc đổi tên field, chuyển package hoặc thay cách khởi tạo object có thể làm hỏng tích hợp mà compiler không phát hiện được như với API public thông thường.

**Khó xác định nguyên nhân khi có lỗi**

Khi một module mở toàn bộ, quyền reflection của framework rộng hơn nhu cầu thực tế. Việc xem xét module descriptor sẽ khó trả lời package nào cần được mở và framework nào đang phụ thuộc vào chi tiết nào.

**Giảm hiệu quả của ranh giới module**

Một mục tiêu của JPMS là công khai API có chủ đích và giữ implementation bên trong module. Mở toàn bộ package làm giảm lợi ích của việc phân tách đó, dù không biến tất cả package thành API compile-time.

Vì vậy, hãy bắt đầu từ package cần framework xử lý, rồi chỉ mở phạm vi cần thiết.

## 6. Ví dụ cấu hình module cho ứng dụng dùng ORM và JSON

Giả sử module orders có các package:

~~~text
com.example.orders
├── api
├── model
├── repository
├── internal
└── config
~~~

Ứng dụng có module ORM và JSON mapper. Nếu cả hai framework chỉ cần truy cập sâu vào entity trong package model, descriptor có thể viết:

~~~java
module com.example.orders {
    requires com.example.orm;
    requires com.example.json;

    exports com.example.orders.api;

    opens com.example.orders.model to
        com.example.orm,
        com.example.json;
}
~~~

Kết quả:

- Module tiêu thụ có thể dùng API public trong package api.
- ORM và JSON mapper có thể reflection sâu vào package model.
- Package repository, internal và config không được mở theo directive trên.
- Nếu sau này một framework cần package khác, module sở hữu có thể đánh giá và thêm đúng package đó.

Nếu framework chỉ cần API public, có thể không cần mở package cho framework đó. Đừng thêm opens chỉ vì thư viện có sử dụng reflection ở một vị trí nào đó; hãy xác định package và thao tác reflection thực tế.

## 7. Dùng --add-opens khi cần cấu hình ở runtime

Trong một số hệ thống, không thể hoặc chưa thể sửa **module-info.java** của module sở hữu package. Java cung cấp tùy chọn runtime **--add-opens** để bổ sung quyền mở package.

Cú pháp:

~~~bash
java --add-opens source.module/package.name=target.module ...
~~~

Ví dụ mở package model của module orders cho module ORM:

~~~bash
java --add-opens com.example.orders/com.example.orders.model=com.example.orm \
     --module com.example.app/com.example.app.Main
~~~

Nếu framework được nạp từ classpath và thuộc unnamed module, có thể dùng **ALL-UNNAMED** làm module đích:

~~~bash
java --add-opens com.example.orders/com.example.orders.model=ALL-UNNAMED \
     --module com.example.app/com.example.app.Main
~~~

Tùy chọn này áp dụng ở runtime và có thể hữu ích khi tích hợp thư viện cũ hoặc xử lý một module bên thứ ba mà bạn không sở hữu. Tuy nhiên, nó nên được giới hạn theo package và module đích, đồng thời được ghi rõ trong cấu hình chạy để dễ kiểm soát.

Khi module sở hữu package nằm trong ứng dụng của bạn, khai báo **opens** hoặc **opens ... to ...** trong module descriptor thường là cách thể hiện yêu cầu rõ ràng hơn. Không nên giữ các tùy chọn **--add-opens** rộng trong script chạy nếu ứng dụng không còn cần chúng.

## 8. Phân biệt exports, opens và open module

Ba khái niệm thường bị nhầm lẫn:

**exports**

Cho phép module khác truy cập các kiểu public trong package theo quy tắc Java. Đây là cách công khai API compile-time/runtime thông thường.

~~~java
module com.example.orders {
    exports com.example.orders.api;
}
~~~

**opens**

Cho phép reflection sâu vào package ở runtime. Có thể mở cho tất cả module hoặc chỉ module đích.

~~~java
module com.example.orders {
    opens com.example.orders.model to com.example.orm;
}
~~~

**open module**

Mở mọi package trong module cho reflection sâu. Nó không tự động export package cho truy cập thông thường.

~~~java
open module com.example.orders {
    exports com.example.orders.api;
}
~~~

Nếu lỗi là không thể import một class public từ module khác, hãy kiểm tra **exports** và **requires**. Nếu lỗi là framework không thể truy cập private field hoặc constructor bằng reflection, hãy kiểm tra **opens** và module đích. Dùng đúng directive sẽ giữ được ranh giới module rõ ràng.

## 9. Quy trình xác định package nào cần mở

Khi framework báo lỗi reflection, có thể xử lý theo các bước:

1. Đọc exception để xác định tên module sở hữu class, package bị chặn và module đang thực hiện reflection.
2. Xác định framework cần truy cập sâu vào package nào, class nào và thao tác nào.
3. Kiểm tra module descriptor của module sở hữu package.
4. Nếu package đã được mở, xác minh module đích trong qualified opens có đúng module name của framework không.
5. Nếu chưa mở, thêm **opens package to framework.module** cho package cần thiết.
6. Chạy lại ứng dụng để xác nhận thao tác reflection hoạt động.
7. Nếu phải dùng **--add-opens** tạm thời, ghi nhận chính xác package và module đích, sau đó cân nhắc chuyển cấu hình vào module descriptor khi có thể.

Không nên sửa bằng cách đổi cả module thành open module ngay khi gặp một lỗi reflection. Một lỗi ở package model không chứng minh rằng các package api, internal, repository và config đều cần mở.

## 10. Lỗi thường gặp

**Dùng opens nhưng module khác vẫn không import được class**

Opens chỉ hỗ trợ reflection sâu ở runtime. Để import và gọi API public, cần exports và quan hệ đọc module phù hợp.

**Dùng exports nhưng framework vẫn không truy cập được private field**

Exports không thay thế opens. Hãy mở package cần reflection cho module framework.

**Qualified opens không có tác dụng**

Tên module đích có thể sai hoặc framework đang được nạp trong unnamed module. Kiểm tra module name thực tế và cân nhắc **ALL-UNNAMED** chỉ khi đúng là framework thuộc classpath.

**Mở một package nhưng lỗi chuyển sang package khác**

Framework có thể đang xử lý nhiều loại entity hoặc metadata nằm ở package khác. Chỉ mở package mới sau khi xác định nó thực sự cần reflection; không chuyển ngay sang open module toàn bộ.

**Đổi sang open module nhưng API vẫn không truy cập được**

Open module mở package cho reflection, không export mọi package. Nếu module khác cần dùng API public, vẫn phải khai báo exports cho package đó.

**Không thể kết hợp open module và các opens directive riêng**

Khi descriptor dùng modifier **open**, mọi package đã được mở cho reflection. Nếu cần phạm vi mở chọn lọc, hãy bỏ modifier open và khai báo các directive opens cụ thể.

## 11. Ghi nhớ

- **opens package** mở một package cho reflection sâu ở runtime.
- **opens package to module** chỉ cấp quyền reflection sâu cho module đích đã chỉ định.
- **open module** mở tất cả package của module cho reflection sâu, nhưng không export chúng thành API compile-time.
- **exports** và **opens** giải quyết hai loại truy cập khác nhau.
- Nên mở package model hoặc package tích hợp cụ thể mà framework cần, thay vì mở toàn bộ module.
- **--add-opens** là tùy chọn runtime hữu ích cho cấu hình chuyển tiếp; cần giới hạn đúng package và module đích.
- Một package được mở vẫn là package do module sở hữu; module descriptor thể hiện rõ phạm vi tích hợp và giúp kiểm soát thay đổi implementation.

Khi thiết kế module, hãy xác định framework cần reflection vào đâu rồi khai báo qualified opens cho đúng package. Cách làm này giữ phần API công khai và phần implementation tách biệt, đồng thời giảm các phụ thuộc ngầm vào cấu trúc nội bộ của module.
