# Automatic module hình thành từ JAR thiếu module descriptor

Trong Java Platform Module System (JPMS), một thư viện JAR chưa có `module-info.class` vẫn có thể được đưa vào module path và sử dụng như một module. Java gọi loại module này là **automatic module**.

Automatic module là cơ chế hỗ trợ chuyển đổi thư viện từ classpath sang module path. Nó cho phép module mới phụ thuộc vào JAR cũ mà chưa cần sửa ngay mã nguồn của thư viện đó. Tuy nhiên, automatic module có ranh giới truy cập rộng hơn explicit named module, vì vậy nên xem đây là bước chuyển tiếp và đánh giá kỹ trước khi dùng lâu dài.

Có một điểm thuật ngữ cần phân biệt: một **modular JAR** đúng nghĩa đã có module descriptor. Automatic module hình thành từ một JAR chưa có descriptor, tức một thư viện JAR chưa được modular hóa tường minh, khi JAR đó được đặt trên module path.

## Mục tiêu

Sau bài học, bạn có thể:

- Giải thích điều kiện để một JAR trở thành automatic module.
- Phân biệt JAR trên classpath, automatic module và explicit named module.
- Xác định tên automatic module từ manifest hoặc tên file JAR.
- Hiểu phạm vi đọc và export rộng của automatic module.
- Khai báo `requires` tới automatic module từ một named module.
- Kiểm tra automatic module bằng các công cụ của JDK và lập lộ trình chuyển sang explicit module.

## 1. Automatic module là gì?

Một JAR không chứa module descriptor có thể được Java xem như automatic module khi đặt trên module path.

Module descriptor tường minh thường là file `module-info.class` ở gốc JAR. File này được tạo từ mã nguồn `module-info.java` và khai báo tên module, dependency, package export, opens, uses và provides.

Nếu JAR không có descriptor tường minh và được đặt trên module path, Java suy ra một module name và áp dụng các quy tắc mặc định của automatic module.

Ví dụ:

~~~text
libs/
└── legacy-utils-2.4.1.jar
~~~

Giả sử JAR `legacy-utils-2.4.1.jar` không có `module-info.class`. Khi đặt thư mục `libs` trên module path, Java có thể xem JAR này như một automatic module.

Điều quan trọng là vị trí của JAR:

- JAR nằm trên classpath: các class thuộc unnamed module tương ứng với class loader.
- JAR không có module descriptor nằm trên module path: JAR được xem như automatic module.
- JAR có module descriptor nằm trên module path: JAR là explicit named module.

Chỉ chuyển một JAR từ classpath sang module path đã có thể làm thay đổi cách Java tổ chức và giải quyết dependency của nó.

## 2. Xác định tên automatic module

Automatic module cần có một tên để module khác có thể khai báo `requires tên-module;`. Java xác định tên theo thứ tự ưu tiên.

### 2.1. Dùng Automatic-Module-Name trong manifest

Nhà phát hành thư viện có thể khai báo thuộc tính `Automatic-Module-Name` trong file manifest của JAR.

Ví dụ nội dung `META-INF/MANIFEST.MF`:

~~~text
Manifest-Version: 1.0
Automatic-Module-Name: com.acme.legacyutils
~~~

Khi JAR không có module descriptor nhưng có thuộc tính này, Java dùng `com.acme.legacyutils` làm tên automatic module.

Ưu điểm:

- Tên module ổn định qua các lần đổi phiên bản JAR.
- Tên file có thể thay đổi mà client vẫn dùng cùng tên trong `requires`.
- Nhà phát hành có thể chọn tên theo namespace của tổ chức.
- Người sử dụng không phải phụ thuộc vào thuật toán suy ra tên từ filename.

Lưu ý: `Automatic-Module-Name` chỉ cung cấp tên module. Nó không phải module descriptor và không khai báo dependency, exports hay opens. JAR vẫn là automatic module cho tới khi có module descriptor tường minh.

### 2.2. Suy ra tên từ filename

Nếu manifest không có `Automatic-Module-Name`, Java suy ra tên từ tên file JAR.

Ví dụ:

~~~text
legacy-utils-2.4.1.jar
~~~

Tên module được suy ra có thể là:

~~~text
legacy.utils
~~~

Quá trình suy ra tên về cơ bản gồm:

1. Bỏ phần mở rộng `.jar`.
2. Nhận diện và loại bỏ hậu tố phiên bản ở cuối tên nếu có dạng phiên bản được hỗ trợ.
3. Thay các ký tự không phải chữ hoặc số bằng dấu chấm.
4. Gộp các dấu chấm liên tiếp và loại bỏ dấu chấm ở đầu hoặc cuối.

Ví dụ khác:

| Tên JAR | Tên automatic module minh họa |
|---|---|
| `legacy-utils-2.4.1.jar` | `legacy.utils` |
| `http-client.jar` | `http.client` |
| `acme_json-1.2.jar` | `acme.json` |

Kết quả chính xác phụ thuộc quy tắc suy ra tên của JDK và filename thực tế. Vì vậy, hãy kiểm tra bằng công cụ JDK thay vì tự đoán tên trong module descriptor.

### 2.3. Vì sao nên đặt Automatic-Module-Name?

Nếu tên module phụ thuộc filename, việc đổi tên artifact hoặc cách đóng gói có thể làm tên module suy ra thay đổi. Những module đã khai báo `requires` theo tên cũ sẽ phải cập nhật.

Nhà phát hành thư viện nên đặt `Automatic-Module-Name` ổn định ngay cả khi chưa chuyển sang explicit module. Khi sau này bổ sung `module-info.class` với cùng tên, client có thể tiếp tục sử dụng cùng tên module.

## 3. Đặc điểm truy cập của automatic module

Automatic module được thiết kế để giúp thư viện cũ hoạt động trong module system với ít thay đổi nhất. Vì vậy, nó có các quy tắc mặc định rộng hơn explicit named module.

### 3.1. Tất cả package được export

Automatic module được xem như export tất cả package của nó. Module khác đọc automatic module có thể sử dụng các kiểu đủ điều kiện trong những package đó theo quy tắc truy cập Java.

Ví dụ JAR có cấu trúc:

~~~text
legacy-utils.jar
└── com/acme/legacy/
    ├── api/LegacyClient.class
    └── internal/ConnectionPool.class
~~~

Nếu JAR trở thành automatic module, cả package `com.acme.legacy.api` và `com.acme.legacy.internal` đều được export theo quy tắc automatic module.

Điều này có nghĩa package có tên `internal` không được bảo vệ như package nội bộ của explicit named module. Nếu class trong package đó đủ quyền truy cập Java, module khác đọc automatic module có thể tham chiếu tới nó.

Vì vậy, automatic module chưa cung cấp mức đóng gói chặt như module có descriptor tường minh.

### 3.2. Automatic module đọc các module khác trong cấu hình

Automatic module được xem là đọc mọi module khác trong cấu hình module, bao gồm các module có tên và unnamed module nếu có.

Điều này giúp JAR cũ có thể tiếp tục tham chiếu tới các dependency vốn được đặt trên classpath trong quá trình chuyển đổi. Tuy nhiên, quan hệ đọc rộng làm cho dependency thực tế khó thể hiện rõ trong đồ thị.

Ví dụ:

~~~text
com.acme.app ──requires──> legacy.utils

legacy.utils có thể đọc các module khác
trong cấu hình module của ứng dụng.
~~~

Module app vẫn phải khai báo `requires legacy.utils;` để đọc automatic module. Quy tắc automatic module tự đọc rộng không có nghĩa mọi named module khác đều tự động đọc được automatic module.

### 3.3. Không có module descriptor để kiểm soát ranh giới

Automatic module không có `module-info.class` tường minh để khai báo:

- Các dependency cụ thể bằng `requires`.
- Package công khai bằng `exports`.
- Package mở cho reflection bằng `opens`.
- Service được tiêu thụ bằng `uses`.
- Service provider bằng `provides ... with ...`.

Các hành vi mặc định của automatic module thay thế một phần các khai báo này trong giai đoạn tương thích. Đó là lý do automatic module thuận tiện khi chuyển đổi nhưng không phải lựa chọn tốt nhất để kiểm soát kiến trúc lâu dài.

## 4. Dùng automatic module từ named module

Giả sử có thư viện cũ:

~~~text
libs/
└── legacy-utils-2.4.1.jar
~~~

JAR không có `module-info.class` và manifest không khai báo `Automatic-Module-Name`. Theo tên file, Java suy ra module name là `legacy.utils`.

Module app có thể khai báo:

~~~java
module com.acme.app {
    requires legacy.utils;
}
~~~

Sau đó mã nguồn có thể import class trong package được automatic module export:

~~~java
package com.acme.app;

import com.acme.legacy.api.LegacyClient;

public class Main {
    public static void main(String[] args) {
        LegacyClient client = new LegacyClient();
        client.execute();
    }
}
~~~

Để biên dịch, đặt JAR trên module path cùng với source module:

~~~bash
javac --module-path "libs" --module-source-path src -d out -m com.acme.app
~~~

Trên Windows, dấu phân cách giữa nhiều vị trí module path là dấu chấm phẩy. Trên Linux và macOS, dùng dấu hai chấm.

Chạy ứng dụng trên Windows:

~~~bash
java --module-path "out;libs" -m com.acme.app/com.acme.app.Main
~~~

Chạy ứng dụng trên Linux hoặc macOS:

~~~bash
java --module-path "out:libs" -m com.acme.app/com.acme.app.Main
~~~

Nếu tên automatic module thực tế không phải `legacy.utils`, khai báo `requires` phải dùng đúng tên mà Java xác định. Dùng `jar --describe-module` để kiểm tra.

## 5. Phân biệt classpath, automatic module và explicit module

Cùng một JAR có thể được xử lý khác nhau tùy vị trí và nội dung:

| Trường hợp | Cách Java xem xét |
|---|---|
| JAR không có descriptor trên classpath | Class thuộc unnamed module |
| JAR không có descriptor trên module path | Automatic module |
| JAR có module descriptor trên module path | Explicit named module |
| JAR chỉ có `Automatic-Module-Name` nhưng không có descriptor trên module path | Vẫn là automatic module, dùng tên trong manifest |

Một số điểm cần nhớ:

- Đặt JAR lên classpath không kích hoạt automatic module.
- Thuộc tính `Automatic-Module-Name` không biến JAR thành explicit named module.
- Một JAR có `module-info.class` và nằm trên module path được xem là explicit module.
- Automatic module không có ranh giới exports được thiết kế rõ ràng như explicit module.

Sự khác biệt này quan trọng khi chuyển ứng dụng từ classpath sang module path. Một ứng dụng có thể biên dịch được ở cấu hình cũ nhưng phát sinh lỗi nếu các dependency không được đặt đúng vị trí hoặc tên module suy ra khác với tên đã khai báo.

## 6. Kiểm tra automatic module bằng công cụ JDK

### 6.1. Dùng jar --describe-module

Kiểm tra JAR:

~~~bash
jar --describe-module --file libs/legacy-utils-2.4.1.jar
~~~

Với JAR không có descriptor, đầu ra cho biết không tìm thấy module descriptor và module được suy ra là automatic module. Công cụ cũng hiển thị tên module được xác định.

Nếu JAR có manifest chứa `Automatic-Module-Name`, kiểm tra tên được hiển thị để dùng đúng trong `requires`.

### 6.2. Liệt kê module có thể quan sát

Có thể dùng:

~~~bash
java --module-path libs --list-modules
~~~

Lệnh này liệt kê các module hệ thống và module có thể quan sát từ module path được cung cấp. Tìm tên automatic module trong danh sách để xác nhận Java nhận diện artifact.

### 6.3. Kiểm tra dependency của JAR

Dùng `jdeps` để xem các dependency mà bytecode của thư viện tham chiếu:

~~~bash
jdeps --module-path libs --list-deps libs/legacy-utils-2.4.1.jar
~~~

Để xem phân tích ở cấp module hoặc package, điều chỉnh tùy chọn `jdeps` theo mục tiêu. Kết quả giúp phát hiện dependency mà thư viện cũ đang sử dụng, nhưng vẫn cần kiểm tra cấu hình runtime và các cơ chế nạp class động.

## 7. Hạn chế của automatic module

### 7.1. API bị công bố quá rộng

Vì tất cả package được export, module khác có thể bắt đầu phụ thuộc vào những class vốn được tác giả thư viện xem là implementation.

Ví dụ, client có thể import class từ package `internal`. Khi thư viện chuyển sang explicit module và chỉ export package API, client đó sẽ không còn biên dịch được.

### 7.2. Dependency không được khai báo rõ ràng

Automatic module đọc các module khác trong cấu hình. Điều này có thể che giấu một số dependency chưa được mô hình hóa trong module descriptor.

Khi chuyển sang explicit module, những dependency thực sự cần thiết phải được khai báo rõ ràng. Các thiếu sót có thể chỉ xuất hiện sau khi ranh giới module được siết chặt.

### 7.3. Khó đánh giá hợp đồng API

Không có danh sách export tường minh khiến người duy trì khó xác định package nào được hỗ trợ như API lâu dài. Client có thể phụ thuộc vào bất kỳ package nào mà automatic module công bố.

### 7.4. Tên suy ra có thể không ổn định

Nếu tên module được suy ra từ filename, đổi tên JAR có thể làm tên module thay đổi. Việc khai báo `Automatic-Module-Name` giúp ổn định tên trong giai đoạn chuyển tiếp.

## 8. Lộ trình chuyển từ automatic module sang explicit module

Khi thư viện đã sẵn sàng modular hóa, có thể chuyển dần theo quy trình:

1. Xác định tên module ổn định, ưu tiên tên đã được công bố qua `Automatic-Module-Name`.
2. Kiểm kê package và các API mà client đang sử dụng.
3. Dùng `jdeps` để hỗ trợ tìm dependency ở cấp module.
4. Viết `module-info.java` với các chỉ thị `requires` phù hợp.
5. Chỉ export package thực sự là API; giữ implementation ở package không export.
6. Thêm `opens` nếu framework cần deep reflection.
7. Khai báo `uses` và `provides` nếu module tham gia ServiceLoader.
8. Biên dịch và chạy các client để phát hiện dependency hoặc package access bị thiếu.
9. Phát hành explicit modular JAR và kiểm tra lại tên module mà client sử dụng.

JDK có công cụ hỗ trợ sinh module descriptor ban đầu:

~~~bash
jdeps --generate-module-info generated-modules libs/legacy-utils-2.4.1.jar
~~~

Mã được sinh chỉ là điểm khởi đầu. Cần xem lại các dependency, package export, reflection và service configuration trước khi sử dụng descriptor trong bản phát hành.

Sau khi JAR có descriptor tường minh và được đặt trên module path, nó trở thành explicit named module. Khi đó, dependency và ranh giới package được kiểm soát theo module descriptor thay vì các quy tắc rộng của automatic module.

## 9. Tự kiểm tra

**Tình huống 1:** Một JAR không có `module-info.class` được đặt trên classpath. Nó có tự động trở thành automatic module không?

**Trả lời:** Không. JAR trên classpath thuộc unnamed module. Automatic module hình thành khi JAR không có descriptor được đặt trên module path.

**Tình huống 2:** Một JAR không có descriptor nhưng manifest có `Automatic-Module-Name: com.acme.legacy`. Tên module được dùng là gì?

**Trả lời:** `com.acme.legacy`. JAR vẫn là automatic module vì manifest chỉ cung cấp tên, không thay thế module descriptor.

**Tình huống 3:** Automatic module có export package nội bộ không?

**Trả lời:** Theo quy tắc automatic module, tất cả package của nó được export. Đây là một trong những lý do automatic module có ranh giới đóng gói rộng hơn explicit module.

**Tình huống 4:** Module app có cần khai báo `requires legacy.utils;` khi muốn sử dụng automatic module đó không?

**Trả lời:** Có. Quy tắc đọc rộng của automatic module áp dụng cho chiều automatic module đọc các module khác; nó không tự tạo quan hệ đọc ngược từ app đến automatic module.

**Tình huống 5:** Thư viện đã có `Automatic-Module-Name` có phải là explicit named module không?

**Trả lời:** Không. Nếu thiếu `module-info.class`, thư viện vẫn là automatic module khi nằm trên module path.

**Tình huống 6:** Vì sao nên chuyển automatic module sang explicit module khi có thể?

**Trả lời:** Explicit module cho phép khai báo dependency và package export rõ ràng, giảm bề mặt API bị công bố và giúp phát hiện sớm dependency không hợp lệ.

Khi gặp một JAR cũ, hãy kiểm tra vị trí đặt JAR, sự hiện diện của `module-info.class`, manifest và tên module mà JDK suy ra. Từ đó xác định nó là unnamed module, automatic module hay explicit named module trước khi thiết kế các dòng `requires` của ứng dụng.