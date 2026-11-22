# Một JAR với lớp nền và các phần triển khai theo phiên bản

## Mục tiêu

Một thư viện có thể cần chạy trên nhiều bản Java nhưng vẫn muốn tận dụng API hoặc tối ưu riêng của các JDK mới hơn. Java hỗ trợ cách đóng gói này bằng **Multi-Release JAR (MR-JAR)**: một file JAR chứa lớp nền và các bản thay thế được đặt trong thư mục theo phiên bản runtime.

Khi chạy, Java chọn lớp trong thư mục phiên bản cao nhất không vượt quá phiên bản runtime hiện tại. Nếu không có bản thay thế phù hợp, runtime dùng lớp nền ở gốc JAR. Nhờ vậy, nhà phát triển có thể phát hành một artifact duy nhất với nhiều phần triển khai.

Bài này trình bày:

- Cấu trúc của một Multi-Release JAR.
- Vai trò của thuộc tính manifest Multi-Release.
- Cách biên dịch lớp nền và lớp theo phiên bản bằng javac --release.
- Cách đóng gói các lớp bằng jar --release.
- Cách runtime chọn lớp phù hợp.
- Cách đặt module descriptor theo phiên bản trong modular MR-JAR.
- Cách kiểm tra tính nhất quán API và kiểm thử consumer.

## 1. Multi-Release JAR giải quyết vấn đề gì?

Giả sử thư viện có API:

~~~java
package com.acme.greeting.api;

public final class Greeting {
    public static String message() {
        return "Hello";
    }
}
~~~

Phần lớn runtime có thể dùng một cách triển khai chung. Tuy nhiên, trên JDK mới, thư viện có thể muốn dùng API mới hoặc một implementation được tối ưu cho phiên bản đó.

Nếu phát hành riêng từng file JAR, người dùng phải chọn đúng artifact theo phiên bản Java. MR-JAR cho phép đặt nhiều bản triển khai vào cùng một file:

~~~text
com.acme.greeting.jar
├── META-INF/
│   ├── MANIFEST.MF
│   └── versions/
│       ├── 17/
│       │   └── module-info.class
│       └── 21/
│           └── com/acme/greeting/api/Greeting.class
└── com/
    └── acme/
        └── greeting/
            └── api/
                └── Greeting.class
~~~

Trong ví dụ:

- Lớp ở gốc là bản nền, biên dịch cho phiên bản Java tối thiểu mà thư viện hỗ trợ.
- module-info.class nằm trong thư mục phiên bản 17, vì đây là bản descriptor dành cho runtime từ Java 17 trở lên.
- Lớp Greeting trong versions/21 thay thế lớp nền trên Java 21 trở lên.

Một JAR có thể có nhiều thư mục phiên bản, chẳng hạn 17, 21 và 25. Không cần tạo một file JAR riêng cho mỗi phiên bản.

## 2. Manifest bắt buộc: Multi-Release: true

Một JAR chỉ được runtime xử lý theo quy tắc multi-release khi manifest có thuộc tính:

~~~text
Manifest-Version: 1.0
Multi-Release: true
~~~

Giá trị phải là true. Nếu thiếu thuộc tính này hoặc giá trị không đúng, các file nằm trong META-INF/versions sẽ không được xem là bản thay thế theo phiên bản runtime.

Manifest được đặt tại META-INF/MANIFEST.MF và nằm ở gốc JAR. Ví dụ tạo file MANIFEST.MF bằng UTF-8 hoặc ASCII:

~~~text
Manifest-Version: 1.0
Multi-Release: true
~~~

Dùng tùy chọn --manifest của jar để đưa manifest vào archive. Không đặt một manifest khác trong thư mục versions để bật chế độ multi-release; cờ này thuộc manifest gốc của JAR.

## 3. Runtime chọn lớp như thế nào?

Với một lớp có tên đầy đủ tương ứng với đường dẫn:

~~~text
com/acme/greeting/api/Greeting.class
~~~

runtime thực hiện việc chọn phiên bản theo nguyên tắc:

1. Xác định phiên bản runtime Java hiện tại.
2. Tìm thư mục META-INF/versions có số phiên bản không vượt quá runtime.
3. Chọn bản có số phiên bản lớn nhất trong các bản phù hợp.
4. Nếu không tìm thấy bản thay thế phù hợp, dùng entry ở gốc JAR.

Ví dụ:

| Runtime | Bản được chọn |
|---|---|
| Java 17 | Lớp nền ở gốc JAR |
| Java 20 | Lớp trong versions/17 nếu có |
| Java 21 | Lớp trong versions/21 |
| Java 24 | Lớp trong versions/21 nếu không có versions/24 hoặc cao hơn phù hợp |

Runtime không chọn bản có số phiên bản lớn hơn runtime. Một JDK 17 không thể nạp class file được biên dịch cho Java 21 chỉ vì file đó nằm trong cùng JAR.

Các thư mục phiên bản hợp lệ bắt đầu từ 9. Mỗi thư mục dùng số phiên bản Java tương ứng, ví dụ META-INF/versions/17/ hoặc META-INF/versions/21/.

## 4. Giữ API nhất quán giữa các phiên bản

Lớp thay thế thường có thể thay đổi cách triển khai, nhưng phải giữ hợp đồng API mà consumer sử dụng.

Ví dụ hợp lệ:

- Bản nền và bản Java 21 đều có public static String message().
- Phần thân method khác nhau để tận dụng API hoặc tối ưu riêng của runtime.
- Consumer vẫn biên dịch với cùng tên lớp, method và kiểu dữ liệu.

Ví dụ không nên làm:

- Bản Java 21 thêm public method mà bản nền không có.
- Bản Java 21 đổi kiểu trả về hoặc xóa constructor public.
- Một phiên bản thay đổi chữ ký public khiến consumer chỉ chạy trên một số JDK.

Consumer được biên dịch dựa trên một phiên bản API. Nếu runtime nạp bản thay thế có API khác, chương trình có thể gặp lỗi linkage như NoSuchMethodError hoặc lỗi tương thích khác.

Dùng lệnh sau để kiểm tra JAR:

~~~bash
jar --validate --file com.acme.greeting.jar
~~~

jar --validate kiểm tra cấu trúc multi-release và tính nhất quán API giữa các phiên bản. Nếu một lớp trong thư mục phiên bản có API khác bản trước đó, công cụ JAR có thể báo entry không nhất quán và từ chối archive.

Hãy giữ API ổn định và thay đổi implementation bên trong. Nếu thật sự cần một API khác, nên phát hành một phiên bản thư viện hoặc module contract mới thay vì làm cùng một MR-JAR có chữ ký public phụ thuộc runtime.

## 5. Biên dịch lớp nền và lớp thay thế

Mỗi phần cần được biên dịch với release phù hợp.

- Lớp nền dùng javac --release cho phiên bản tối thiểu được hỗ trợ.
- Lớp thay thế dùng javac --release cho phiên bản mà thư mục đó đại diện.
- Không biên dịch lớp phiên bản mới bằng target cũ rồi gọi API mới qua reflection không cần thiết.

Ví dụ bài này chọn Java 17 làm baseline và cung cấp implementation khác từ Java 21.

### Lớp nền

Tệp base-src/com/acme/greeting/api/Greeting.java:

~~~java
package com.acme.greeting.api;

public final class Greeting {
    public static String message() {
        return "Base implementation";
    }
}
~~~

Biên dịch:

~~~bash
javac --release 17 -d base-out base-src/com/acme/greeting/api/Greeting.java
~~~

Các class file trong base-out tương thích với runtime Java 17 trở lên.

### Lớp dành cho Java 21 trở lên

Tệp v21-src/com/acme/greeting/api/Greeting.java:

~~~java
package com.acme.greeting.api;

public final class Greeting {
    public static String message() {
        return "Java 21+ implementation";
    }
}
~~~

Biên dịch:

~~~bash
javac --release 21 -d v21-out v21-src/com/acme/greeting/api/Greeting.java
~~~

Lớp này có cùng package, tên lớp và chữ ký method public với lớp nền. Runtime Java 21 trở lên có thể chọn bản này.

Có thể dùng implementation riêng để tận dụng API mới, vectorization, I/O hoặc một thuật toán phù hợp runtime mới. Mã nền vẫn phải hoạt động độc lập trên phiên bản tối thiểu được hỗ trợ.

## 6. Đóng gói bằng jar --release

Công cụ jar hỗ trợ tùy chọn --release khi tạo hoặc cập nhật MR-JAR. Tùy chọn này đặt các file theo sau vào:

~~~text
META-INF/versions/<VERSION>/
~~~

Ví dụ:

~~~bash
jar --create --file com.acme.greeting.jar \
    --manifest MANIFEST.MF \
    -C base-out . \
    --release 21 -C v21-out .
~~~

Kết quả:

- Nội dung của base-out nằm ở gốc JAR.
- Nội dung của v21-out nằm dưới META-INF/versions/21.
- Manifest ở gốc xác định JAR là multi-release.

Có thể kiểm tra:

~~~bash
jar --list --file com.acme.greeting.jar
~~~

Các entry quan trọng sẽ tương tự:

~~~text
META-INF/MANIFEST.MF
com/acme/greeting/api/Greeting.class
META-INF/versions/21/com/acme/greeting/api/Greeting.class
~~~

Nếu JAR có nhiều bản thay thế, lặp lại --release cho từng phiên bản:

~~~bash
jar --create --file com.acme.greeting.jar \
    --manifest MANIFEST.MF \
    -C base-out . \
    --release 17 -C v17-out . \
    --release 21 -C v21-out . \
    --release 25 -C v25-out .
~~~

Trong lệnh trên, mỗi -C chỉ định thư mục nguồn cho nhóm file tiếp theo. --release chuyển các file sau nó vào thư mục phiên bản tương ứng. Hãy kiểm tra danh sách entry sau khi đóng gói để bảo đảm file không bị đặt nhầm vị trí.

## 7. Multi-Release JAR có module descriptor

Một modular MR-JAR có thể đặt module descriptor trong thư mục phiên bản. Cách này hữu ích khi JAR cần giữ cấu trúc tương thích với một runtime cũ hơn không hiểu module descriptor.

Ví dụ nếu descriptor áp dụng từ Java 17:

~~~text
META-INF/
├── MANIFEST.MF
└── versions/
    └── 17/
        └── module-info.class
~~~

Không cần đặt module-info.class ở gốc JAR trong trường hợp descriptor được cung cấp theo phiên bản. Runtime Java 17 trở lên sẽ đọc descriptor trong thư mục phiên bản phù hợp khi manifest đánh dấu JAR là multi-release.

Nếu descriptor cần có hiệu lực từ Java 9, đặt nó trong META-INF/versions/9/ và biên dịch descriptor cho release 9. Nếu thư viện chỉ hỗ trợ runtime Java 17 trở lên, có thể đặt descriptor ở versions/17 như ví dụ dưới đây.

### Module descriptor

Tệp module-info.java:

~~~java
module com.acme.greeting {
    exports com.acme.greeting.api;
}
~~~

Biên dịch descriptor cho Java 17. Vì các package API đã được biên dịch vào base-out, dùng --patch-module để javac biết nội dung mô-đun khi kiểm tra exports:

~~~bash
javac --release 17 \
    --patch-module com.acme.greeting=base-out \
    -d v17-out module-info.java
~~~

Sau bước này, v17-out chứa module-info.class. Đóng gói descriptor cùng lớp nền và implementation Java 21:

~~~bash
jar --create --file com.acme.greeting.jar \
    --manifest MANIFEST.MF \
    -C base-out . \
    --release 17 -C v17-out module-info.class \
    --release 21 -C v21-out com/acme/greeting/api/Greeting.class
~~~

Cấu trúc JAR có dạng:

~~~text
com.acme.greeting.jar
├── META-INF/MANIFEST.MF
├── com/acme/greeting/api/Greeting.class
└── META-INF/versions/
    ├── 17/module-info.class
    └── 21/com/acme/greeting/api/Greeting.class
~~~

Từ Java 17, JAR được nhận diện bằng tên mô-đun com.acme.greeting. Runtime Java 17 dùng lớp nền; Java 21 trở lên dùng lớp thay thế trong versions/21.

Nếu cần cùng một tên mô-đun ở các runtime trước khi descriptor phiên bản được nhận diện, hãy công bố tên automatic module ổn định bằng Automatic-Module-Name trong manifest và giữ tên đó trùng với tên trong module-info.java. Chỉ dùng chiến lược này khi thư viện thực sự hỗ trợ các runtime đó.

### Kiểm tra descriptor theo phiên bản

Vì module descriptor không nằm ở gốc JAR, hãy chỉ rõ phiên bản khi kiểm tra:

~~~bash
jar --describe-module --file com.acme.greeting.jar --release 17
~~~

Kết quả cần cho biết tên com.acme.greeting, package được exports và dependency java.base. Nếu không truyền --release, jar tool có thể báo không có root module descriptor và yêu cầu chỉ rõ release.

## 8. Consumer dùng cùng một API trên module path

Ứng dụng tiêu thụ chỉ cần biết module name và API công khai.

Tệp app-src/com.acme.app/module-info.java:

~~~java
module com.acme.app {
    requires com.acme.greeting;
}
~~~

Tệp app-src/com.acme.app/com/acme/app/Main.java:

~~~java
package com.acme.app;

import com.acme.greeting.api.Greeting;

public class Main {
    public static void main(String[] args) {
        System.out.println(Greeting.message());
    }
}
~~~

Biên dịch consumer bằng Java 17:

~~~bash
javac --release 17 \
    --module-path com.acme.greeting.jar \
    -d app-out \
    --module-source-path app-src \
    -m com.acme.app
~~~

Chạy bằng JDK 24:

~~~bash
java --module-path "com.acme.greeting.jar;app-out" \
    -m com.acme.app/com.acme.app.Main
~~~

Stdout:

~~~text
Java 21+ implementation
~~~

JDK 24 chọn lớp trong versions/21. Mã nguồn consumer vẫn gọi cùng method Greeting.message() mà không cần biết JAR có nhiều implementation.

Nếu chạy trên JDK 17, runtime sẽ dùng lớp nền ở gốc JAR và stdout sẽ là:

~~~text
Base implementation
~~~

## 9. Kiểm tra runtime version selection

Có thể dùng JarFile API để xem entry nào được chọn cho một phiên bản Java cụ thể. Constructor nhận Runtime.Version cho phép kiểm tra cách JarFile nhìn archive theo runtime version đó.

Ví dụ InspectJar.java:

~~~java
import java.io.File;
import java.util.jar.JarEntry;
import java.util.jar.JarFile;
import java.util.zip.ZipFile;

public class InspectJar {
    public static void main(String[] args) throws Exception {
        Runtime.Version target = Runtime.Version.parse(args[1]);

        try (JarFile jar = new JarFile(
                new File(args[0]),
                true,
                ZipFile.OPEN_READ,
                target)) {

            JarEntry entry = jar.getJarEntry(
                    "com/acme/greeting/api/Greeting.class");

            System.out.println(entry.getRealName());
        }
    }
}
~~~

Biên dịch helper:

~~~bash
javac --release 17 InspectJar.java
~~~

Kiểm tra cách nhìn JAR cho Java 17:

~~~bash
java InspectJar com.acme.greeting.jar 17
~~~

Output:

~~~text
com/acme/greeting/api/Greeting.class
~~~

Kiểm tra cho Java 24:

~~~bash
java InspectJar com.acme.greeting.jar 24
~~~

Output:

~~~text
META-INF/versions/21/com/acme/greeting/api/Greeting.class
~~~

Kết quả cho thấy Java 17 dùng lớp nền, còn Java 24 chọn bản thay thế Java 21. Đây là cách kiểm tra entry selection mà không cần cài nhiều JDK để chạy cùng một bài thử.

## 10. Kiểm tra JAR trước khi phát hành

Nên kiểm tra ít nhất bốn khía cạnh.

### Kiểm tra manifest

~~~bash
jar --extract --file com.acme.greeting.jar META-INF/MANIFEST.MF
~~~

Mở manifest và xác nhận có:

~~~text
Multi-Release: true
~~~

### Kiểm tra cấu trúc entry

~~~bash
jar --list --file com.acme.greeting.jar
~~~

Xác nhận lớp nền nằm ở gốc và lớp thay thế nằm trong đúng thư mục phiên bản.

### Kiểm tra API giữa các phiên bản

~~~bash
jar --validate --file com.acme.greeting.jar
~~~

Đảm bảo public API của các lớp thay thế nhất quán. Chạy kiểm tra này trong pipeline trước khi phát hành artifact.

### Kiểm tra module descriptor

~~~bash
jar --describe-module --file com.acme.greeting.jar --release 17
~~~

Xác nhận đúng tên mô-đun, exports và requires. Sau đó biên dịch và chạy một consumer modular với chính JAR đã đóng gói, không chỉ với thư mục class file trong quá trình build.

## 11. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Runtime luôn dùng lớp nền | Manifest thiếu Multi-Release: true hoặc entry nằm sai đường dẫn | Kiểm tra manifest và jar --list |
| Runtime báo UnsupportedClassVersionError | Lớp phiên bản mới bị nạp trên runtime quá cũ hoặc đặt nhầm ở gốc JAR | Đặt lớp trong đúng META-INF/versions/N |
| Java 21 không chọn bản Java 21 | Thư mục không tên versions/21 hoặc JAR không được đánh dấu multi-release | Kiểm tra cấu trúc và manifest |
| Consumer gặp NoSuchMethodError | API của lớp thay thế khác lớp nền | Giữ chữ ký public nhất quán và chạy jar --validate |
| JAR không được nhận diện là modular | module-info.class đặt sai vị trí hoặc release descriptor không được chọn | Kiểm tra manifest và dùng jar --describe-module --release N |
| Module name không như mong đợi | Tên trong module-info hoặc Automatic-Module-Name không nhất quán | Giữ tên mô-đun ổn định và xác minh descriptor |
| Tính năng mới không hoạt động trên runtime cũ | Code mới vô tình nằm trong lớp nền hoặc dependency không tương thích | Đưa implementation mới vào đúng version directory và giữ base implementation tương thích |

Một lỗi nguy hiểm là chỉ kiểm thử JAR trên JDK mới nhất. Điều đó có thể bỏ sót lỗi trong lớp nền. Hãy kiểm thử tối thiểu runtime baseline và runtime mới nhất mà thư viện tuyên bố hỗ trợ.

## 12. Nguyên tắc thiết kế và phát hành

- Chọn rõ phiên bản Java tối thiểu mà thư viện hỗ trợ.
- Biên dịch lớp nền bằng javac --release tương ứng với baseline.
- Biên dịch từng implementation thay thế bằng release mà thư mục đại diện.
- Luôn có Multi-Release: true trong manifest gốc.
- Giữ package, tên lớp và API công khai tương thích giữa các phiên bản.
- Đặt module-info.class vào version directory phù hợp với runtime cần nhận descriptor.
- Dùng jar --validate và jar --describe-module trong pipeline.
- Kiểm thử consumer trên baseline và trên runtime có implementation mới.
- Không để lớp biên dịch cho JDK mới xuất hiện ở gốc JAR nếu runtime baseline không hỗ trợ class file đó.
- Ghi lại các phiên bản Java mà artifact đã được kiểm thử.

## Kết luận

Multi-Release JAR cho phép một file JAR chứa lớp nền và các implementation dành riêng cho phiên bản Java mới hơn. Manifest Multi-Release: true bật cơ chế lựa chọn; META-INF/versions/N chứa các bản thay thế; runtime chọn bản cao nhất không vượt quá phiên bản đang chạy.

Với modular MR-JAR, module descriptor cũng có thể được đặt trong thư mục phiên bản để runtime phù hợp nhận diện mô-đun. Hãy giữ API nhất quán, biên dịch từng phần bằng --release, kiểm tra bằng jar --validate, rồi chạy consumer trên các runtime mục tiêu. Cách này giúp một artifact duy trì hợp đồng API chung trong khi vẫn tận dụng được implementation phù hợp với từng thế hệ Java.
