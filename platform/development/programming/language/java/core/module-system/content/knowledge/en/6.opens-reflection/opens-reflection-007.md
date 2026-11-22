# Strong encapsulation và lỗi InaccessibleObjectException

**Strong encapsulation** là cơ chế JPMS giới hạn việc truy cập vào các package của named module. Một module chỉ công khai API cho module khác qua những package được export; deep reflection vào thành viên không public chỉ được phép khi package được mở phù hợp. Cơ chế này giúp module kiểm soát ranh giới triển khai và giảm sự phụ thuộc vào chi tiết nội bộ.

Khi framework hoặc thư viện dùng reflection để truy cập một package chưa được mở, ứng dụng có thể gặp `java.lang.reflect.InaccessibleObjectException`. Đây là lỗi thường thấy khi chuyển ứng dụng cũ sang Java có module system hoặc khi nâng cấp JDK và một thư viện vẫn cố truy cập thành viên nội bộ.

Bài này tập trung vào cách nhận diện nguyên nhân, phân biệt `exports` với `opens`, chọn cách sửa phù hợp và kiểm tra cấu hình trên JDK 21.

## 1. Strong encapsulation bảo vệ điều gì?

Trước JPMS, nhiều ứng dụng dựa vào classpath và reflection để truy cập các lớp hoặc thành viên vốn không được thiết kế làm API công khai. Một framework có thể gọi `setAccessible(true)` trên field private, hoặc truy cập package nội bộ của thư viện khác. Cách làm này thường phụ thuộc vào chi tiết triển khai và có thể bị phá vỡ khi thư viện thay đổi.

JPMS đưa ranh giới module vào mô hình truy cập của JVM. Với một named module:

- Package không được export không thể được module khác dùng như API thông thường.
- Package không được mở không cho phép module khác thực hiện deep reflection vào các thành viên không public.
- Các access modifier của Java như `public`, `protected`, package-private và `private` vẫn có hiệu lực bên trong ranh giới module.
- Một module có thể quyết định package nào là API công khai, package nào chỉ mở cho framework hoặc module tích hợp cụ thể.

Strong encapsulation giúp ngăn ứng dụng phụ thuộc vào nội bộ của module khác, đặc biệt là nội bộ JDK. Khi JDK thay đổi implementation, ứng dụng dựa trên API được hỗ trợ sẽ ổn định hơn ứng dụng truy cập các lớp hoặc field nội bộ.

### Strong encapsulation trong các phiên bản JDK

JPMS xuất hiện từ JDK 9. Quá trình chuyển đổi ban đầu có một số cơ chế tương thích để ứng dụng cũ tiếp tục chạy. JDK 16 áp dụng strong encapsulation mặc định rộng hơn đối với các API nội bộ của JDK; JDK 17 hoàn tất việc đóng gói mạnh các nội bộ JDK theo JEP 403.

Từ JDK 17, tùy chọn `--illegal-access` không còn khôi phục cách truy cập mở rộng như các bản JDK đầu của JPMS. Ứng dụng cần xử lý từng package cụ thể bằng API được hỗ trợ, khai báo `opens` hoặc tùy chọn `--add-opens` có phạm vi rõ ràng.

## 2. InaccessibleObjectException xuất hiện khi nào?

`InaccessibleObjectException` là unchecked exception trong package `java.lang.reflect`. Nó có thể xuất hiện khi mã gọi `AccessibleObject.setAccessible(true)` nhưng JVM không cho phép bỏ qua kiểm tra truy cập cho đối tượng reflection đó.

Ví dụ, thư viện có một lớp domain:

~~~java
package com.acme.domain.model;

public class Customer {
    private String name = "An";
}
~~~

Một framework ở module khác muốn đọc field private bằng reflection:

~~~java
import java.lang.reflect.Field;

Field field = Customer.class.getDeclaredField("name");
field.setAccessible(true);
Object value = field.get(customer);
~~~

Nếu package `com.acme.domain.model` nằm trong named module và chưa được mở cho module chứa framework, lệnh `setAccessible(true)` có thể ném `InaccessibleObjectException`.

Lỗi này không có nghĩa field private tự nhiên trở thành public. Reflection đang yêu cầu JVM cho phép bỏ qua kiểm tra truy cập thông thường; JPMS từ chối yêu cầu đó vì package chưa được mở cho caller.

### setAccessible và trySetAccessible

Hai API thường được dùng để điều khiển khả năng truy cập của đối tượng reflection:

- `setAccessible(true)` cố gắng bật quyền truy cập đã được bỏ qua. Nếu module system không cho phép, phương thức có thể ném `InaccessibleObjectException`.
- `trySetAccessible()` thử bật quyền truy cập và trả về `true` nếu thành công, `false` nếu không thể bật. Cách này phù hợp khi thư viện muốn xử lý trường hợp không được mở mà không dùng exception làm luồng điều khiển chính.

Ví dụ:

~~~java
Field field = Customer.class.getDeclaredField("name");

if (field.trySetAccessible()) {
    Object value = field.get(customer);
    System.out.println(value);
} else {
    System.out.println("Package is not open for deep reflection");
}
~~~

`trySetAccessible()` không tự mở package và cũng không thay đổi module descriptor. Nó chỉ báo liệu caller hiện tại có được phép bật quyền truy cập hay không.

## 3. Phân biệt exports với opens

`exports` và `opens` đều khai báo ở cấp package trong module descriptor, nhưng giải quyết hai loại truy cập khác nhau.

| Directive | Mục đích | Trường hợp sử dụng |
|---|---|---|
| `exports package.name` | Công khai API public của package cho module khác | Mã nguồn module khác import và gọi kiểu public |
| `opens package.name` | Cho phép deep reflection vào package ở runtime | Framework cần đọc/ghi field private hoặc gọi thành viên không public |
| `exports package.name to target.module` | Chỉ công khai API cho module được chỉ định | Giới hạn nhóm module được phép sử dụng API |
| `opens package.name to target.module` | Chỉ mở reflection cho module được chỉ định | Giới hạn framework/module được truy cập sâu |

Một package được export không mặc nhiên được mở cho deep reflection. Ngược lại, một package được mở cho reflection không mặc nhiên trở thành API mà module khác có thể import ở thời điểm biên dịch.

Ví dụ module domain:

~~~java
module com.acme.domain {
    exports com.acme.domain.api;
    opens com.acme.domain.model to com.acme.json;
}
~~~

Trong cấu hình này:

- Mọi module đọc được `com.acme.domain` có thể truy cập kiểu public trong `com.acme.domain.api`.
- Chỉ module `com.acme.json` được deep reflection vào `com.acme.domain.model`.
- Các package khác của module domain vẫn được đóng kín theo mặc định.

Nếu framework chạy trên classpath, caller của reflection thuộc unnamed module. Khi cần mở package cho các thư viện classpath, có thể dùng tùy chọn launcher `--add-opens` với đích `ALL-UNNAMED`.

## 4. Vì sao một package cần được mở?

Một số framework hoạt động bằng cách khám phá cấu trúc lớp và truy cập thành viên mà mã ứng dụng không gọi trực tiếp. Các trường hợp phổ biến:

- **Serialization/deserialization:** framework cần đọc hoặc gán field không public để ánh xạ object với JSON/XML.
- **Dependency injection:** container cần tìm constructor, field hoặc method được đánh dấu annotation và có thể cần truy cập thành viên không public.
- **ORM/persistence:** framework ánh xạ cột dữ liệu vào field hoặc gọi constructor theo quy ước của nó.
- **Testing/mock:** công cụ kiểm thử cần thay đổi trạng thái nội bộ hoặc truy cập thành viên private để hỗ trợ một số kỹ thuật test.
- **Reflection-based mapping:** thư viện phân tích class metadata và gọi accessor hoặc thành viên theo cấu hình.

Không phải mọi thao tác reflection đều cần `opens`. Truy cập public API thông qua package đã export có thể không cần deep reflection. Nhu cầu mở package phát sinh khi framework phải vượt qua access check thông thường để tiếp cận thành viên không public.

Hãy xác định chính xác package và module caller từ stack trace. Một lỗi do framework truy cập `java.base/java.lang` khác với lỗi do framework truy cập package domain của ứng dụng; cách xử lý và mức độ ảnh hưởng cũng khác nhau.

## 5. Đọc stack trace để tìm package cần mở

Thông báo lỗi thường có dạng:

~~~text
java.lang.reflect.InaccessibleObjectException:
Unable to make field private final ... accessible:
module java.base does not "opens java.lang" to unnamed module
~~~

Thông báo cho biết ba thông tin quan trọng:

1. **Module nguồn:** trong ví dụ là `java.base`, module chứa lớp/field mà framework muốn truy cập.
2. **Package nguồn:** `java.lang` là package cần được mở.
3. **Module đích:** `unnamed module` là module của caller, thường là thư viện đang chạy trên classpath.

Nếu lỗi xuất phát từ module ứng dụng, thông báo có thể cho biết tên module ứng dụng và package domain, ví dụ:

~~~text
module com.acme.domain does not "opens com.acme.domain.model"
to module com.acme.json
~~~

Từ thông tin này, xác định:

- Module nào sở hữu lớp/field đang bị truy cập.
- Package chứa lớp đó.
- Module nào thực hiện reflection.
- Framework có phiên bản hỗ trợ JPMS hoặc cách tích hợp khác hay không.

Đừng vội mở package dựa trên tên lớp cuối cùng trong stack trace. Dòng thông báo về module và package cho biết chính xác ranh giới JPMS đang chặn truy cập.

## 6. Cách xử lý ưu tiên

### Cập nhật framework hoặc thư viện

Trước tiên hãy kiểm tra phiên bản framework. Phiên bản cũ có thể dựa vào reflection trên implementation nội bộ của JDK hoặc truy cập package mà phiên bản mới đã thay đổi. Bản nâng cấp có thể đã chuyển sang API được hỗ trợ, điều chỉnh chiến lược reflection hoặc bổ sung cấu hình module phù hợp.

Đây thường là hướng xử lý bền vững nhất vì không làm rộng quyền truy cập của module.

### Dùng API công khai được hỗ trợ

Nếu ứng dụng đang truy cập lớp nội bộ của JDK, hãy tìm API công khai thay thế. Ví dụ, thay vì thao tác trực tiếp trên implementation class hoặc field nội bộ, dùng API chính thức của JDK.

Không nên phụ thuộc vào tên lớp nội bộ, field private của JDK hoặc package không được export. Các chi tiết này có thể thay đổi giữa các phiên bản Java.

### Mở đúng package trong module descriptor

Nếu framework thực sự cần deep reflection vào package do ứng dụng sở hữu, hãy khai báo qualified opens:

~~~java
module com.acme.domain {
    exports com.acme.domain.api;
    opens com.acme.domain.model to com.acme.json;
}
~~~

Module `com.acme.json` cần là caller thực tế của reflection. Chỉ mở package cần thiết cho framework đó. Các package khác vẫn giữ encapsulation.

Nếu nhiều framework cần deep reflection vào cùng package, có thể liệt kê nhiều module đích:

~~~java
module com.acme.domain {
    opens com.acme.domain.model to
        com.acme.json,
        com.acme.persistence;
}
~~~

### Dùng open module khi có nhu cầu rộng

Có thể khai báo:

~~~java
open module com.acme.domain {
    exports com.acme.domain.api;
}
~~~

Một open module mở tất cả package của nó cho deep reflection ở runtime. Cách này có thể phù hợp với một ứng dụng/framework được thiết kế dựa trên reflection rộng khắp, nhưng làm giảm khả năng đóng gói của toàn module.

Nếu chỉ một vài package cần được framework truy cập, ưu tiên `opens package.name to module.name` để phạm vi rõ ràng hơn. Không khai báo các directive `opens` riêng lẻ bên trong một `open module`.

## 7. Dùng --add-opens khi cần điều chỉnh lúc khởi chạy

Khi không thể sửa module descriptor của thư viện hoặc đang chuyển đổi hệ thống, Java launcher cung cấp tùy chọn `--add-opens`:

~~~text
--add-opens source.module/package=target.module
~~~

Ví dụ mở package `java.lang` của `java.base` cho tất cả unnamed module:

~~~bash
java --add-opens java.base/java.lang=ALL-UNNAMED -jar app.jar
~~~

Nếu framework là named module, chỉ định tên module đích thay cho `ALL-UNNAMED`:

~~~bash
java --add-opens com.acme.domain/com.acme.domain.model=com.acme.json \
     --module-path mods \
     -m com.acme.app/com.acme.app.Main
~~~

Trong lệnh này:

- `com.acme.domain` là module chứa package cần mở.
- `com.acme.domain.model` là package cần cho phép deep reflection.
- `com.acme.json` là module thực hiện reflection.

`ALL-UNNAMED` là tên đích đặc biệt của tùy chọn launcher, có nghĩa áp dụng cho tất cả unnamed module. Nó thường dùng khi framework chạy trên classpath. Đây không phải tên module hợp lệ để ghi trong directive `opens ... to ...` của `module-info.java`.

Tùy chọn `--add-opens` chỉ có tác dụng cho tiến trình được khởi chạy với tùy chọn đó. Nó không sửa file JAR, không thay đổi `module-info.class` và không tự áp dụng cho tiến trình Java khác như test worker, plugin process hoặc service được khởi chạy riêng.

Trong Gradle, cần đặt JVM argument vào đúng task/process chạy ứng dụng hoặc test. Chỉ thêm tùy chọn vào lệnh chạy ứng dụng không bảo đảm test worker cũng nhận được cấu hình đó.

## 8. Phân biệt --add-opens với --add-exports

Hai tùy chọn thường bị dùng nhầm:

- `--add-exports` cho phép truy cập các kiểu public trong package chưa được export tới module đích. Nó hỗ trợ truy cập API public qua module boundary.
- `--add-opens` mở package cho deep reflection vào thành viên không public ở runtime.

Ví dụ:

~~~bash
# Cho phép truy cập kiểu public trong package
java --add-exports java.base/sun.security.util=ALL-UNNAMED ...

# Cho phép deep reflection vào package
java --add-opens java.base/java.lang=ALL-UNNAMED ...
~~~

Nếu lỗi nói package chưa được export khi biên dịch hoặc liên kết mã, hãy xem xét `exports` hoặc `--add-exports`. Nếu lỗi xảy ra khi framework gọi `setAccessible(true)` vào field/constructor/method không public, hãy xem xét `opens` hoặc `--add-opens`.

Không dùng `--add-exports` như giải pháp thay thế cho lỗi deep reflection. Export package không đồng nghĩa mở quyền truy cập sâu vào các thành viên private.

## 9. Vì sao --illegal-access không còn là giải pháp?

Trong các bản JDK đầu có JPMS, tùy chọn `--illegal-access` từng hỗ trợ tương thích cho một số truy cập reflective tới package nội bộ của JDK. Cơ chế này đã được chuyển đổi qua các phiên bản và strong encapsulation được áp dụng mặc định từ JDK 16; JDK 17 hoàn tất việc đóng gói mạnh các nội bộ JDK.

Trên JDK 17 trở lên, `--illegal-access` không còn khôi phục chế độ truy cập mở rộng cũ. Việc thêm tùy chọn này không phải cách sửa phù hợp cho `InaccessibleObjectException`. Hãy xác định module/package đích và dùng API công khai hoặc `--add-opens` có phạm vi cụ thể khi thực sự cần.

## 10. Quy trình chẩn đoán theo từng bước

Khi gặp `InaccessibleObjectException`, thực hiện lần lượt:

1. **Đọc thông báo đầy đủ:** ghi lại module nguồn, package nguồn và module đích được nêu trong exception.
2. **Xác định caller:** tìm framework/thư viện thực hiện lời gọi reflection trong stack trace; kiểm tra nó là named module hay unnamed module.
3. **Xác định nhu cầu thực tế:** framework có cần truy cập thành viên private hay chỉ cần API public?
4. **Kiểm tra descriptor:** dùng `jar --describe-module --file ...` hoặc đọc `module-info.java` để xem package đã export/open hay chưa.
5. **Ưu tiên cập nhật hoặc đổi API:** loại bỏ phụ thuộc vào implementation nội bộ nếu có API được hỗ trợ.
6. **Mở package có giới hạn:** thêm qualified `opens` vào module descriptor hoặc truyền `--add-opens` vào đúng JVM process.
7. **Chạy lại đúng môi trường:** kiểm tra ứng dụng, test worker, Gradle task hoặc process riêng đều nhận cấu hình cần thiết.
8. **Thu hẹp cấu hình sau chuyển đổi:** nếu đã nâng cấp framework và không còn cần mở package, loại bỏ tùy chọn tạm thời.

Có thể dùng `jdeps` để rà soát phụ thuộc vào API nội bộ của JDK:

~~~bash
jdeps --jdk-internals app.jar
~~~

Lệnh này giúp phát hiện một số tham chiếu tới JDK internal APIs trong bytecode. Nó không thay thế việc đọc stack trace vì lỗi reflection có thể phát sinh từ framework hoặc dependency được nạp động.

## 11. Checklist trước khi phát hành

- [ ] Xác định đúng module và package bị chặn từ exception.
- [ ] Xác định module caller là named module hay unnamed module.
- [ ] Kiểm tra framework có bản tương thích với JDK/module system đang dùng.
- [ ] Ưu tiên API public thay vì truy cập implementation nội bộ.
- [ ] Nếu cần reflection, chỉ mở package cần thiết.
- [ ] Dùng qualified `opens` cho module đích cụ thể khi có thể.
- [ ] Đặt `--add-opens` vào đúng tiến trình JVM, kể cả test worker nếu cần.
- [ ] Không nhầm `--add-exports` với `--add-opens`.
- [ ] Không dựa vào `--illegal-access` trên JDK hiện đại.
- [ ] Ghi lại lý do và phạm vi của mọi package được mở để có thể thu hẹp về sau.

## 12. Ghi nhớ

Strong encapsulation là ranh giới bảo vệ package của named module. `InaccessibleObjectException` thường xuất hiện khi mã reflection cố truy cập sâu vào package chưa được mở cho module caller. `public` và `exports` giải quyết truy cập API thông thường; `opens` và `--add-opens` giải quyết nhu cầu deep reflection.

Hãy bắt đầu từ module/package/caller trong thông báo lỗi, kiểm tra nhu cầu của framework, rồi ưu tiên cập nhật thư viện hoặc dùng API được hỗ trợ. Chỉ mở đúng package và đúng module đích khi reflection thực sự cần thiết. Cách xử lý có phạm vi rõ ràng giúp ứng dụng tiếp tục dùng được framework mà vẫn giữ được phần lớn lợi ích encapsulation của JPMS.
