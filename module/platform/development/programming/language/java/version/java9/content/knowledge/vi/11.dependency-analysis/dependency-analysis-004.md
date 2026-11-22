# Kiểm tra descriptor và phụ thuộc thừa bằng jdeps --check

JPMS (Java Platform Module System) dùng module descriptor để khai báo các module mà một module cần đọc, package được công bố và quan hệ dịch vụ. Theo thời gian, descriptor có thể giữ lại một directive requires không còn cần thiết hoặc một qualified export mà module nhận quyền không thực sự sử dụng.

Công cụ jdeps đi kèm JDK có tùy chọn --check để phân tích module đã biên dịch. Tùy chọn này giúp đối chiếu descriptor hiện tại với phụ thuộc được suy ra từ bytecode, xem đồ thị phụ thuộc sau khi rút gọn và phát hiện qualified export không được dùng.

Có hai việc cần phân biệt:

- **requires thừa:** so sánh phần Module descriptor với Suggested module descriptor. Một requires có trong descriptor hiện tại nhưng vắng mặt trong đề xuất có thể không cần cho các phụ thuộc tĩnh mà jdeps nhìn thấy.
- **qualified exports không dùng:** jdeps có thể liệt kê rõ trong phần Unused qualified exports những package đang export có giới hạn tới module không sử dụng package đó.

jdeps chỉ phân tích và đưa ra thông tin. Công cụ không tự sửa module-info.java hay ghi đè JAR.

## 1. jdeps --check dùng để làm gì?

jdeps là công cụ phân tích dependency của Java, được phân phối cùng JDK. Tùy chọn --check phân tích một hoặc nhiều named module được chỉ định theo tên module.

Cú pháp cơ bản:

~~~bash
jdeps --module-path mods --check com.example.app
~~~

Trong đó:

- jdeps là công cụ phân tích phụ thuộc của JDK.
- --module-path mods chỉ định nơi chứa các module ứng dụng và thư viện cần phân tích.
- --check yêu cầu phân tích module được nêu tên.
- com.example.app là tên module trong module descriptor, không nhất thiết trùng tên file JAR.

Có thể kiểm tra nhiều module trong một lần bằng danh sách tên module phân tách bởi dấu phẩy:

~~~bash
jdeps --module-path mods --check com.example.app,com.example.api
~~~

Khi cần đọc kết quả rõ ràng, nên chạy từng module riêng để dễ đối chiếu descriptor của module nào với đề xuất tương ứng.

### 1.1. Các phần quan trọng trong output

Tùy phiên bản JDK và module được kiểm tra, output có thể có các phần:

| Phần output | Ý nghĩa |
|---|---|
| Module descriptor | Các directive hiện có trong module descriptor đã biên dịch |
| Suggested module descriptor | Descriptor được đề xuất dựa trên phân tích dependency |
| Transitive reduced graph | Đồ thị module sau khi loại bỏ các cạnh đọc được suy ra gián tiếp |
| Unused qualified exports | Các qualified exports mà module nhận quyền không sử dụng package được export |

Ví dụ phần descriptor:

~~~text
[Module descriptor]
  requires com.example.api;
  requires mandated java.base (@24.0.2);
  requires java.sql (@24.0.2);
~~~

Đây là các requires hiện tại mà jdeps đọc được từ module đã biên dịch.

Phần đề xuất:

~~~text
[Suggested module descriptor for com.example.client]
  requires com.example.api;
  requires mandated java.base;
~~~

Nếu java.sql xuất hiện trong Module descriptor nhưng không xuất hiện trong Suggested module descriptor, jdeps không tìm thấy phụ thuộc bytecode cần thiết tới java.sql trong phạm vi phân tích module đó. Đây là dấu hiệu để xem xét loại bỏ requires java.sql.

Dòng mandated java.base là phụ thuộc nền tảng được module system quy định ngầm định. Không nên hiểu nó như một requires thừa do người viết dự án thêm vào.

### 1.2. Transitive reduced graph là gì?

Module có thể đọc một module gián tiếp thông qua requires transitive. Ví dụ, nếu A đọc B và B khai báo requires transitive C, thì A cũng có thể đọc C theo đồ thị module.

Transitive reduced graph trình bày đồ thị sau khi loại bỏ những cạnh đọc đã được suy ra từ các cạnh transitive khác. Phần này giúp nhìn các quan hệ phụ thuộc cần thiết trong cấu hình module mà không lặp lại mọi cạnh đọc được ngầm định.

Không nên nhầm đồ thị rút gọn với danh sách toàn bộ JAR hoặc thư viện được đóng gói trong ứng dụng. Đây là đồ thị quan hệ đọc giữa module.

## 2. Kiểm tra requires không còn cần thiết

Một module có thể từng sử dụng một thư viện rồi sau đó mã nguồn thay đổi. Directive requires vẫn còn trong module-info.java dù bytecode hiện tại không còn tham chiếu tới module đó.

Ví dụ module client khai báo:

~~~java
module com.example.client {
    requires com.example.api;
    requires java.sql;
}
~~~

Giả sử các lớp của com.example.client chỉ gọi API trong com.example.api và không sử dụng lớp nào của java.sql. jdeps có thể đề xuất descriptor không còn requires java.sql.

### 2.1. Cách đọc phần Suggested module descriptor

Khi chạy:

~~~bash
jdeps --module-path out --check com.example.client
~~~

Đối chiếu hai phần:

~~~text
[Module descriptor]
  requires com.example.api;
  requires mandated java.base (@24.0.2);
  requires java.sql (@24.0.2);

[Suggested module descriptor for com.example.client]
  requires com.example.api;
  requires mandated java.base;
~~~

Ở ví dụ này:

- com.example.api vẫn có trong đề xuất vì bytecode client sử dụng API từ module đó.
- java.sql có trong descriptor hiện tại nhưng không có trong đề xuất.
- java.base là module nền tảng cơ bản và được đánh dấu mandated.

Đề xuất cho thấy requires java.sql có thể đang dư thừa đối với bytecode được phân tích.

### 2.2. Không xóa requires chỉ dựa trên một dòng output

jdeps phân tích phụ thuộc tĩnh mà nó có thể quan sát từ class đã biên dịch và module descriptor. Nó không thể suy ra mọi nhu cầu runtime do cấu hình bên ngoài quyết định.

Trước khi xóa một requires, cần kiểm tra:

- Ứng dụng có nạp class bằng tên chuỗi qua reflection hay không.
- Framework có đọc cấu hình để nạp implementation hoặc driver hay không.
- Service provider có được phát hiện qua uses/provides hay cấu hình service hay không.
- Module có cung cấp API public dùng kiểu thuộc module dependency hay không.
- Có profile, plugin hoặc đường chạy khác không được đưa vào lần phân tích hay không.

Một dependency không xuất hiện trong bytecode trực tiếp vẫn có thể được sử dụng theo cách động. Hãy xem Suggested module descriptor là gợi ý để review, sau đó chạy kiểm thử trên các cấu hình runtime thực tế.

## 3. Phát hiện qualified exports không được sử dụng

Qualified export giới hạn package được công bố cho một hoặc nhiều module cụ thể.

Ví dụ:

~~~java
module com.example.api {
    exports com.example.api to
        com.example.client,
        com.example.legacy.client;
}
~~~

Trong ví dụ này, cả com.example.client và com.example.legacy.client đều được phép truy cập package com.example.api.

Nếu com.example.legacy.client không sử dụng package đó, qualified export tới module này có thể đã lỗi thời. Khi kiểm tra module API:

~~~bash
jdeps --module-path out --check com.example.api
~~~

jdeps có thể hiển thị:

~~~text
[Unused qualified exports in com.example.api]
  exports com.example.api to com.example.legacy.client
~~~

Điều này cho biết qualified export tới com.example.legacy.client không được sử dụng trong phạm vi các module mà jdeps phân tích.

### 3.1. Vì sao cần kiểm tra module API?

Để tìm requires dư thừa, thường kiểm tra module consumer vì cần biết consumer thực sự dùng module nào.

Để tìm unused qualified exports, kiểm tra module sở hữu package được export. jdeps cần biết descriptor của module nguồn và các module nhận quyền có mặt trong module path.

Không nên chỉ chạy --check trên ứng dụng chính rồi kết luận tất cả qualified exports của thư viện đều đã được kiểm tra. Hãy kiểm tra cả module cung cấp API khi mục tiêu là rà soát exports.

### 3.2. Qualified export không dùng không đồng nghĩa có thể xóa ngay

Trước khi xóa một qualified export:

- Xác nhận module đích có còn được hỗ trợ trong các bản phát hành khác hay không.
- Kiểm tra các plugin hoặc ứng dụng bên ngoài không có mặt trong module path hiện tại.
- Xác nhận module đích không còn dùng package thông qua một cấu hình hoặc phiên bản triển khai khác.
- Đánh giá ảnh hưởng tương thích nếu package từng là hợp đồng được công bố cho module đó.

jdeps chỉ biết những module và bytecode trong phạm vi phân tích. Nó không biết mọi module có thể được triển khai trong tương lai.

Ngoài ra, --check tập trung nhận diện unused qualified exports. Không có cảnh báo không có nghĩa mọi unqualified exports đều đang được dùng; export không giới hạn người nhận không thể được đánh giá đầy đủ chỉ từ một tập module hiện có.

## 4. Ví dụ hoàn chỉnh: tìm requires thừa và qualified export không dùng

Ví dụ gồm ba module:

- com.example.api cung cấp package API và export package đó cho hai client.
- com.example.client sử dụng API nhưng khai báo thêm requires java.sql không cần thiết.
- com.example.legacy.client đọc module API nhưng không sử dụng package được export.

Cấu trúc thư mục:

~~~text
src/
├── com.example.api/
│   ├── module-info.java
│   └── com/example/api/
│       └── Formatter.java
├── com.example.client/
│   ├── module-info.java
│   └── com/example/client/
│       └── Main.java
└── com.example.legacy.client/
    ├── module-info.java
    └── com/example/legacy/
        └── LegacyMain.java
~~~

### 4.1. Module API

File src/com.example.api/module-info.java:

~~~java
module com.example.api {
    exports com.example.api to
        com.example.client,
        com.example.legacy.client;
}
~~~

File src/com.example.api/com/example/api/Formatter.java:

~~~java
package com.example.api;

public final class Formatter {
    private Formatter() {
    }

    public static String upper(String value) {
        return value.toUpperCase(java.util.Locale.ROOT);
    }
}
~~~

Module API công bố package com.example.api cho hai module client.

### 4.2. Module client có dependency thừa

File src/com.example.client/module-info.java:

~~~java
module com.example.client {
    requires com.example.api;
    requires java.sql;
}
~~~

File src/com.example.client/com/example/client/Main.java:

~~~java
package com.example.client;

import com.example.api.Formatter;

public class Main {
    public static void main(String[] args) {
        System.out.println(Formatter.upper("module check"));
    }
}
~~~

Main chỉ sử dụng Formatter. Không có class nào từ java.sql được tham chiếu trong bytecode của module này.

### 4.3. Module legacy client không sử dụng package được export

File src/com.example.legacy.client/module-info.java:

~~~java
module com.example.legacy.client {
    requires com.example.api;
}
~~~

File src/com.example.legacy.client/com/example/legacy/LegacyMain.java:

~~~java
package com.example.legacy;

public class LegacyMain {
    public static void main(String[] args) {
        System.out.println("legacy client does not use the API package");
    }
}
~~~

Module này đọc com.example.api nhưng không import hoặc gọi kiểu nào trong package com.example.api. Vì vậy, qualified export tới module này là ứng viên để loại bỏ sau khi xác nhận phạm vi triển khai.

### 4.4. Biên dịch cả ba module

Từ thư mục chứa src, tạo thư mục đầu ra:

~~~bash
mkdir -p out
javac -d out --module-source-path src -m com.example.api,com.example.client,com.example.legacy.client
~~~

Trên Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
javac -d out --module-source-path src -m com.example.api,com.example.client,com.example.legacy.client
~~~

Chạy client để xác nhận chương trình hoạt động:

~~~bash
java --module-path out -m com.example.client/com.example.client.Main
~~~

Kết quả stdout:

~~~text
MODULE CHECK
~~~

### 4.5. Kiểm tra descriptor của consumer

Chạy:

~~~bash
jdeps --module-path out --check com.example.client
~~~

Output minh họa trên JDK 24:

~~~text
com.example.client
  [Module descriptor]
    requires com.example.api;
    requires mandated java.base (@24.0.2);
    requires java.sql (@24.0.2);
  [Suggested module descriptor for com.example.client]
    requires com.example.api;
    requires mandated java.base;
  [Transitive reduced graph for com.example.client]
    requires com.example.api;
    requires mandated java.base;
~~~

Cách đọc:

- Module descriptor có requires java.sql.
- Suggested module descriptor không còn requires java.sql.
- com.example.api vẫn được giữ lại vì client dùng Formatter.
- java.base là phụ thuộc nền tảng mandated.

Trong ví dụ này, java.sql là dependency dư đối với bytecode của com.example.client. Sau khi review các đường chạy động và cấu hình runtime, có thể sửa module-info.java để bỏ requires java.sql.

### 4.6. Kiểm tra descriptor của module API

Chạy:

~~~bash
jdeps --module-path out --check com.example.api
~~~

Output minh họa:

~~~text
com.example.api
  [Module descriptor]
    requires mandated java.base (@24.0.2);
  [Suggested module descriptor for com.example.api]
    requires mandated java.base;
  [Transitive reduced graph for com.example.api]
    requires mandated java.base;
  [Unused qualified exports in com.example.api]
    exports com.example.api to com.example.legacy.client
~~~

Module com.example.client sử dụng package API nên qualified export tới module này vẫn cần thiết. Module com.example.legacy.client không dùng package nên jdeps liệt kê qualified export tương ứng là unused.

Đường dẫn module và phần version annotation trong output thay đổi theo vị trí dự án và JDK đang chạy. Các phần tiêu đề và directive quan trọng là căn cứ để đối chiếu.

## 5. Cập nhật descriptor sau khi review

Nếu xác nhận java.sql không cần cho runtime hoặc API công khai, sửa module-info.java của client:

~~~java
module com.example.client {
    requires com.example.api;
}
~~~

Nếu xác nhận legacy client không còn là module nhận quyền được hỗ trợ, sửa descriptor API:

~~~java
module com.example.api {
    exports com.example.api to com.example.client;
}
~~~

Sau khi chỉnh sửa:

1. Biên dịch lại toàn bộ module liên quan.
2. Chạy lại ứng dụng và các kiểm thử tích hợp.
3. Chạy jdeps --check trên consumer và module API.
4. Xác nhận suggested descriptor không còn chỉ ra dependency cần xem xét.
5. Xác nhận qualified exports không còn target thừa trong phạm vi module được hỗ trợ.

jdeps không tự thực hiện các thay đổi trên. Người phát triển phải quyết định và chỉnh module-info.java, sau đó biên dịch lại để tạo descriptor mới.

## 6. Giới hạn của jdeps --check

### 6.1. Phân tích tĩnh không thấy mọi dependency động

jdeps phân tích bytecode và module metadata. Một số dependency được tạo ra lúc chạy có thể không xuất hiện dưới dạng tham chiếu class thông thường:

- Class được nạp bằng Class.forName với tên lấy từ file cấu hình.
- Plugin được phát hiện từ thư mục hoặc metadata bên ngoài.
- Driver, implementation hoặc adapter được chọn bằng cấu hình.
- Reflection truy cập lớp hoặc thành viên theo tên.
- Resource và service được tìm qua cơ chế runtime.

Trước khi xóa requires, kiểm tra các đường chạy này. Nếu dependency chỉ phục vụ một profile hoặc plugin tùy chọn, cần ghi rõ phạm vi của cấu hình đó.

### 6.2. Phạm vi module path ảnh hưởng kết quả

Nếu module cần phân tích hoặc module phụ thuộc không có trên module path, jdeps không thể xây dựng đầy đủ đồ thị tương ứng. Hãy đưa các module ứng dụng và thư viện cần thiết vào module path.

Module hệ thống được lấy từ JDK đang chạy, trừ khi cấu hình hệ thống thay thế được chỉ định. Khi phân tích ứng dụng nhắm tới runtime khác, hãy dùng đúng JDK hoặc system module path phù hợp.

### 6.3. Không nhầm --check với các tùy chọn jdeps khác

| Tùy chọn | Mục đích |
|---|---|
| --check module | In descriptor, dependency được phân tích, đồ thị rút gọn và unused qualified exports |
| --list-deps | Liệt kê các module phụ thuộc được phân tích |
| --list-reduced-deps | Liệt kê dependency sau khi bỏ các cạnh đọc được suy ra |
| --print-module-deps | In danh sách tên module phân tách bằng dấu phẩy, hữu ích khi chuẩn bị jlink |
| --missing-deps | Tìm dependency bị thiếu |
| --generate-module-info dir | Sinh module-info.java ban đầu cho JAR chưa modular hóa |

Nếu mục tiêu là review descriptor hiện có và phát hiện qualified export không dùng, dùng --check. Nếu mục tiêu là xem danh sách module cần cho một custom runtime image, --print-module-deps phù hợp hơn.

## 7. Quy trình review dependency đề xuất

1. Xác định đúng module và phiên bản artifact cần kiểm tra.
2. Đảm bảo các module liên quan có mặt trên module path.
3. Chạy jdeps --check cho từng consumer để xem descriptor hiện tại và suggested descriptor.
4. So sánh requires giữa hai phần để xác định dependency cần review.
5. Chạy jdeps --check trên module cung cấp API để xem unused qualified exports.
6. Kiểm tra các dependency được dùng qua reflection, service, cấu hình, plugin hoặc resource.
7. Xác nhận các requires transitive, requires static và service directive vẫn đúng với hợp đồng module.
8. Chỉnh module-info.java sau khi có quyết định kỹ thuật.
9. Biên dịch lại và chạy kiểm thử trên runtime mục tiêu.
10. Chạy lại --check để xác nhận descriptor sau chỉnh sửa.

## 8. Checklist

- [ ] Đã dùng jdeps từ JDK phù hợp với runtime mục tiêu.
- [ ] Module cần kiểm tra có trên module path.
- [ ] Đã đọc phần Module descriptor.
- [ ] Đã đối chiếu phần Suggested module descriptor.
- [ ] Đã review requires có trong descriptor nhưng không còn trong đề xuất.
- [ ] Đã hiểu requires mandated java.base.
- [ ] Đã đọc Transitive reduced graph khi cần kiểm tra quan hệ đọc.
- [ ] Đã chạy --check trên module API để kiểm tra unused qualified exports.
- [ ] Đã xem xét dependency động qua reflection, service, plugin và cấu hình.
- [ ] Không xóa dependency chỉ dựa vào một kết quả phân tích tĩnh.
- [ ] Đã biên dịch lại và chạy kiểm thử sau khi chỉnh descriptor.

## 9. Tài liệu tham khảo

- [Java SE 26 — jdeps command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jdeps.html): cú pháp --check, module path, dependency graph và các tùy chọn phân tích.
- [Java Language Specification, Java SE 26 — Module Declarations](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-7.html): requires, exports, qualified exports và module descriptor.
- [Java Platform Module System — Module Resolution](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-7.html#jls-7.7.5): cách module system phân giải module và quan hệ đọc.
- [Dev.java — Organizing Code into Modules](https://dev.java/learn/organizing/modules/): hướng dẫn thực hành JPMS và thiết kế module.
