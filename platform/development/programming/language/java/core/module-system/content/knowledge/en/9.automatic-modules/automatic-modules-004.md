# Automatic module exports mọi package

Trong Java Platform Module System (JPMS), một thư viện JAR cũ có thể chưa có file **module-info.class** nhưng vẫn được đưa lên module path. Java khi đó xem JAR này như một **automatic module**. Module có tên và có thể được named module khác khai báo bằng **requires**, đồng thời tất cả package của nó được export.

Việc export mọi package giúp thư viện cũ dễ tham gia module graph mà chưa cần sửa source hoặc đóng gói lại ngay. Tuy nhiên, nó cũng làm giảm khả năng kiểm soát ranh giới API: package chứa implementation nội bộ cũng có thể được module khác truy cập nếu có các kiểu public. Đây là đặc điểm quan trọng cần hiểu trước khi dùng automatic module lâu dài.

## 1. Automatic module hình thành khi nào?

Automatic module là một JAR không có module descriptor nhưng được đặt trên **module path**. Java tạo một module có tên từ JAR để các named module có thể phụ thuộc vào nó.

Ví dụ thư viện cũ:

~~~text
libs/
└── legacy-utils-2.4.jar
~~~

JAR này chưa có **module-info.class**. Khi được đưa vào module path, Java có thể nhận diện nó là automatic module. Nếu JAR có manifest khai báo **Automatic-Module-Name**, giá trị đó được dùng làm tên module. Nếu không, Java suy ra tên từ tên file JAR theo quy tắc đặt tên module.

Ví dụ manifest:

~~~text
Manifest-Version: 1.0
Automatic-Module-Name: com.example.legacy
~~~

Tên module ổn định giúp ứng dụng không phụ thuộc vào cách filename được suy ra. Khi đổi tên file hoặc phiên bản artifact, tên suy ra từ filename có thể thay đổi. Thuộc tính **Automatic-Module-Name** giúp tránh thay đổi tên module chỉ vì đổi tên JAR.

## 2. Tất cả package được export có nghĩa gì?

Một named module thông thường phải khai báo từng package muốn công khai:

~~~java
module com.example.library {
    exports com.example.library.api;
}
~~~

Trong trường hợp này, package API được export; package khác không được export sẽ giữ vai trò nội bộ đối với module bên ngoài.

Automatic module không có **module-info.java** để liệt kê các directive **exports**. Thay vào đó, Java xem tất cả package của automatic module là được export. Named module có quan hệ đọc tới automatic module có thể truy cập các kiểu public trong các package đó theo quy tắc Java.

Giả sử JAR chứa:

~~~text
legacy-utils.jar
├── com/example/legacy/api/LegacyClient.class
├── com/example/legacy/model/LegacyRequest.class
└── com/example/legacy/internal/SocketPool.class
~~~

Cả ba package đều được automatic module export. Vì vậy, module ứng dụng có thể truy cập các kiểu public trong package **api**, **model** và cả **internal**, nếu các điều kiện truy cập Java khác được đáp ứng.

Tên package **internal** chỉ là quy ước đặt tên. Nó không tự tạo ra ranh giới bảo vệ trong JPMS. Khi JAR là automatic module, package đó vẫn nằm trong tập package được export.

Điều này khác với named module có descriptor tường minh, nơi tác giả có thể chỉ export package API và giữ package implementation không được export.

## 3. Named module sử dụng automatic module như thế nào?

Một named module có thể khai báo dependency tới automatic module bằng tên module mà JAR công bố.

Ví dụ:

~~~java
module com.example.app {
    requires com.example.legacy;
}
~~~

Code ứng dụng có thể import public type trong các package của thư viện:

~~~java
package com.example.app;

import com.example.legacy.api.LegacyClient;
import com.example.legacy.internal.SocketPool;

public class Main {
    public static void main(String[] args) {
        LegacyClient client = new LegacyClient();
        System.out.println(client.getClass().getName());
    }
}
~~~

Ví dụ import **SocketPool** minh họa hệ quả của việc export mọi package: package có tên internal không được bảo vệ khỏi module tiêu thụ chỉ bởi tên package. Trong ứng dụng thực tế, nên tránh phụ thuộc vào class nội bộ dù compiler cho phép truy cập.

Đưa JAR lên module path và khai báo **requires** là hai việc riêng biệt:

- Module path giúp Java tìm automatic module.
- **requires** tạo quan hệ đọc từ named module sử dụng tới automatic module.
- Việc automatic module export các package cho phép module sử dụng truy cập các kiểu public thuộc những package đó.

Nếu chỉ thêm JAR vào module path mà module ứng dụng không khai báo dependency cần thiết, source vẫn có thể không biên dịch được vì thiếu quan hệ đọc.

## 4. Automatic module export không giới hạn mọi package

Hệ quả lớn nhất là automatic module không cung cấp khả năng chọn lọc package được export.

Giả sử thư viện có cấu trúc:

~~~text
com.vendor.payment
├── api
├── model
├── internal
├── adapter
└── debug
~~~

Nếu JAR được dùng như automatic module, tất cả package trên đều được export. Module tiêu thụ có thể phụ thuộc vào class public trong **internal**, **adapter** hoặc **debug**, dù tác giả thư viện không có ý định coi chúng là API ổn định.

Điều này tạo ra một số rủi ro:

**Phụ thuộc vào implementation**

Ứng dụng có thể import trực tiếp class nội bộ thay vì gọi interface hoặc abstraction công khai. Khi thư viện thay đổi cách triển khai, ứng dụng có thể bị lỗi dù API dự kiến vẫn tương thích.

**Khó thay đổi cấu trúc package**

Một package nội bộ đã bị module khác sử dụng sẽ trở thành một phần của dependency thực tế. Việc đổi tên, di chuyển hoặc xóa class trong package đó có thể gây lỗi biên dịch hoặc runtime.

**Bề mặt API rộng**

Các kiểu public trong nhiều package trở nên có thể truy cập qua ranh giới module. Việc xem xét module descriptor không giúp xác định package nào là API chính thức, bởi automatic module không có danh sách exports do tác giả khai báo.

**Khó kiểm soát tích hợp**

Framework hoặc module tiêu thụ có thể truy cập trực tiếp nhiều chi tiết nội bộ. Điều này làm tăng coupling và khiến việc nâng cấp thư viện khó dự đoán hơn.

Automatic module vì thế phù hợp như một cầu nối để tích hợp thư viện cũ, nhưng không mang lại mức đóng gói chọn lọc như một named module được thiết kế đầy đủ.

## 5. Kiểm tra package và tên của automatic module

Có thể dùng lệnh **jar --describe-module** để xem cách Java nhận diện một JAR:

~~~bash
jar --describe-module --file libs/legacy-utils-2.4.jar
~~~

Với JAR không có module descriptor, kết quả cho biết tên automatic module và trạng thái automatic. Nếu manifest có **Automatic-Module-Name**, tên ổn định đó được sử dụng; nếu không, tên được suy ra từ filename.

Có thể kiểm tra manifest bằng:

~~~bash
jar --describe-module --file libs/legacy-utils-2.4.jar
~~~

Nếu cần xem nội dung manifest, có thể liệt kê hoặc giải nén file **META-INF/MANIFEST.MF** trong JAR. Hãy xác minh module name thực tế trước khi viết **requires**.

Một lưu ý: **Automatic-Module-Name** chỉ ổn định tên module. Nó không tạo ra module descriptor đầy đủ, không giới hạn danh sách package được export và không biến package internal thành package được đóng gói riêng.

## 6. Ví dụ biên dịch và chạy với automatic module

Giả sử thư viện cũ nằm trong **libs/legacy-utils.jar** và công bố tên module **com.example.legacy**. Source ứng dụng:

~~~text
src/
└── com.example.app/
    ├── module-info.java
    └── com/example/app/Main.java
~~~

Module descriptor của ứng dụng:

~~~java
module com.example.app {
    requires com.example.legacy;
}
~~~

Code sử dụng thư viện:

~~~java
package com.example.app;

import com.example.legacy.api.LegacyClient;

public class Main {
    public static void main(String[] args) {
        LegacyClient client = new LegacyClient();
        client.execute();
    }
}
~~~

Biên dịch:

~~~bash
javac --module-path libs \
      --module-source-path src \
      -d out \
      -m com.example.app
~~~

Chạy:

~~~bash
java --module-path "out:libs" \
     --module com.example.app/com.example.app.Main
~~~

Ở đây, thư mục **libs** chứa JAR cũ và Java nhận diện nó như automatic module. Module ứng dụng khai báo **requires com.example.legacy** để có thể sử dụng các kiểu public trong những package được export của thư viện.

Trên Windows, dấu phân cách giữa các phần tử module path là dấu chấm phẩy (**;**); trên Linux và macOS là dấu hai chấm (**:**).

## 7. Automatic module và module thông thường

So sánh automatic module với named module có descriptor:

| Đặc điểm | Automatic module | Named module có module-info.java |
|---|---|---|
| Có tên module | Có | Có |
| Có module descriptor do tác giả khai báo | Không | Có |
| Có thể được dùng trong requires | Có | Có |
| Package được export | Tất cả package | Theo các directive exports |
| Có thể chọn module đích cho exports | Không qua descriptor của automatic module | Có thể dùng qualified exports |
| Dependency được khai báo tường minh trong descriptor | Không | Có |
| Mức kiểm soát API | Rộng, thuận tiện chuyển tiếp | Chủ động và chọn lọc |

Automatic module cũng có khả năng đọc các module khác trong cấu hình module. Đây là hành vi thuận tiện cho thư viện cũ, nhưng làm dependency graph của nó ít tường minh hơn so với một module được thiết kế với các directive **requires** cụ thể.

Không nên nhầm việc automatic module export tất cả package với việc tất cả class hoặc thành viên đều có thể được truy cập. Quy tắc truy cập của Java vẫn áp dụng: kiểu hoặc thành viên cần đáp ứng modifier và điều kiện truy cập tương ứng. Export package cho phép truy cập các kiểu public qua ranh giới module; nó không biến private thành public.

## 8. Khi nào nên giữ automatic module?

Automatic module hữu ích trong một số trường hợp:

- Thư viện bên thứ ba chưa cung cấp module descriptor nhưng ứng dụng cần đặt nó trên module path.
- Ứng dụng đang chuyển dần từ classpath sang JPMS và chưa thể modular hóa mọi dependency.
- Thư viện được đóng gói lại với tên module ổn định qua **Automatic-Module-Name**.
- Cần giữ tương thích trong giai đoạn chuyển đổi trước khi tác giả thư viện hoặc nhóm ứng dụng bổ sung module descriptor.

Khi sử dụng, hãy kiểm tra các package được thư viện cung cấp và tránh import trực tiếp package implementation. Việc code có thể truy cập một class không có nghĩa class đó được tác giả cam kết là API ổn định.

## 9. Khi nào nên tạo module descriptor tường minh?

Nếu bạn sở hữu thư viện hoặc có thể đóng góp thay đổi cho nó, hãy cân nhắc tạo **module-info.java** để kiểm soát package được export.

Ví dụ:

~~~java
module com.example.legacy {
    exports com.example.legacy.api;
}
~~~

Khi module descriptor này được đóng gói vào JAR, module trở thành named module thông thường. Chỉ package **com.example.legacy.api** được export; các package như **internal**, **adapter** hoặc **debug** không được công khai qua ranh giới module.

Lợi ích:

- Xác định rõ hợp đồng API.
- Giữ package implementation ở bên trong module.
- Giảm khả năng module tiêu thụ phụ thuộc vào class nội bộ.
- Khai báo dependency bằng **requires** thay vì dựa vào khả năng đọc rộng của automatic module.
- Có thể dùng **qualified exports** để chỉ công khai package cho một số module đích.

Nếu không thể sửa JAR bên thứ ba, hãy xem xét phiên bản thư viện đã hỗ trợ JPMS hoặc cách đóng gói tương thích được nhà cung cấp công bố. Không nên tự tạo một descriptor không khớp với cấu trúc package và dependency thực tế của thư viện.

## 10. Lỗi thường gặp

**Module không tìm thấy dù JAR đã tồn tại**

Kiểm tra JAR có thực sự nằm trên module path hay chỉ trên classpath. Sau đó kiểm tra module name bằng **jar --describe-module** và đối chiếu với **requires**.

**Không import được package trong JAR**

Nếu JAR là automatic module trên module path, các package của nó được export. Nếu vẫn không truy cập được, hãy kiểm tra quan hệ **requires**, tên module, class có public hay không và JAR có thực sự là automatic module hay không.

**Ứng dụng phụ thuộc vào package internal của thư viện**

Automatic module cho phép truy cập các kiểu public trong mọi package. Hãy chuyển sang API chính thức nếu có thể; nếu sở hữu thư viện, tạo descriptor tường minh để chỉ export package API.

**Đổi tên JAR làm lỗi requires**

Tên suy ra từ filename có thể thay đổi. Dùng manifest **Automatic-Module-Name** ổn định hoặc module descriptor tường minh, rồi cập nhật dependency theo tên module thực tế.

**Có nhiều phiên bản thư viện cùng công bố một module name**

Loại bỏ phiên bản dư thừa và giữ một nguồn module nhất quán. Không nên để nhiều JAR cùng tên module trên module path vì việc phân giải sẽ không còn rõ ràng.

**Nhầm automatic module với unnamed module**

JAR trên module path không có descriptor có thể trở thành automatic module có tên. JAR trên classpath thuộc unnamed module. Hai loại này có hành vi dependency và cách tham chiếu khác nhau.

## 11. Ghi nhớ

- Automatic module hình thành khi JAR không có **module-info.class** được đặt trên module path.
- Automatic module có tên và có thể được named module khác tham chiếu bằng **requires**.
- Tất cả package của automatic module được export, bao gồm package chứa implementation.
- Export package không làm mọi thành viên trở thành public; quy tắc truy cập của Java vẫn được áp dụng.
- **Automatic-Module-Name** ổn định module name nhưng không giới hạn package được export.
- Automatic module phù hợp cho chuyển đổi từng bước; module descriptor tường minh phù hợp khi cần kiểm soát API và dependency.
- Dùng **jar --describe-module** để xác minh tên và loại module trước khi cấu hình **requires**.

Khi tích hợp thư viện cũ, hãy xem automatic module là một cách đưa thư viện vào module graph nhanh chóng. Nếu cần bảo vệ package implementation và duy trì hợp đồng API lâu dài, hãy chuyển thư viện sang named module có descriptor và chỉ export những package thực sự cần công khai.
