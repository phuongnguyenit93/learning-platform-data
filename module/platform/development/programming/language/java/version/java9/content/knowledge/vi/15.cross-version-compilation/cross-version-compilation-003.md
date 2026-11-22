# Chọn phiên bản đích trong tập được compiler hỗ trợ bằng javac --release

Khi biên dịch ứng dụng Java bằng một JDK mới, dự án vẫn có thể cần chạy trên một phiên bản Java cũ hơn. Ví dụ, nhóm phát triển dùng JDK 24 để build nhưng sản phẩm cần tương thích với Java 9. Chỉ đặt mức cú pháp hoặc phiên bản bytecode là chưa đủ: mã nguồn cũng phải tránh gọi API chỉ xuất hiện ở các phiên bản Java mới hơn.

Từ Java 9, javac cung cấp tùy chọn **--release N** để chọn một phiên bản Java SE đích trong tập phiên bản mà compiler hiện tại hỗ trợ. Tùy chọn này đồng bộ ba yếu tố:

- Cú pháp và tính năng ngôn ngữ được phép dùng.
- Phiên bản class file được sinh ra.
- Tập API Java SE mà mã nguồn được phép tham chiếu.

Ví dụ, **javac --release 9** biên dịch theo Java 9, sinh class file tương thích với Java 9 và chỉ cho phép dùng các API Java SE có trong release 9. Phiên bản đích phải nằm trong danh sách compiler hỗ trợ; không thể chọn tùy ý một phiên bản cũ hoặc tương lai.

## 1. Xem tập phiên bản mà compiler hỗ trợ

Tập release hợp lệ phụ thuộc vào phiên bản javac đang chạy. Hãy xem trợ giúp của chính compiler được dùng trong build:

~~~bash
javac --version
javac --help
~~~

Trong phần trợ giúp, javac hiển thị danh sách **Supported releases** cho các tùy chọn --release, --source và --target. Chọn một giá trị nằm trong danh sách đó.

Trên môi trường kiểm thử OpenJDK 24.0.2, danh sách được công bố là:

~~~text
Supported releases:
    8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24
~~~

Danh sách này là kết quả của compiler JDK 24, không phải danh sách cố định cho mọi JDK. Một JDK khác có thể hỗ trợ tập release khác. Khi nâng hoặc hạ JDK trong CI, hãy kiểm tra lại trợ giúp thay vì giả định compiler luôn hỗ trợ cùng các phiên bản.

Ví dụ chọn Java 9:

~~~bash
javac --release 9 -d out src/com/acme/Main.java
~~~

Ví dụ chọn Java 17:

~~~bash
javac --release 17 -d out src/com/acme/Main.java
~~~

Nếu chọn một release không có trong danh sách, javac dừng và báo lỗi như:

~~~text
error: release version 25 not supported
~~~

Thông báo này cho biết compiler hiện tại không thể biên dịch cho release 25. Muốn nhắm đến một phiên bản mới hơn, cần dùng JDK có compiler hỗ trợ phiên bản đó.

## 2. --release kết hợp ba yêu cầu tương thích

Có thể hiểu tùy chọn --release như việc chọn một hợp đồng tương thích cho đầu ra build.

| Thành phần | Điều được chọn | Mục đích |
|---|---|---|
| Source compatibility | Ngôn ngữ của release đích | Ngăn dùng cú pháp hoặc tính năng ra đời sau |
| Target class-file version | Định dạng bytecode của release đích | Để JVM tương ứng có thể đọc class file |
| Java SE API surface | API công khai của release đích | Ngăn gọi phương thức hoặc kiểu chỉ có ở JDK mới hơn |

Ví dụ, khi chọn release 9:

- Có thể dùng các tính năng ngôn ngữ được Java 9 hỗ trợ.
- Compiler tạo class file có major version 53.
- Các API được thêm từ Java 10 trở đi không xuất hiện trong API view của compiler cho release 9.

Điều này quan trọng vì một class file có phiên bản cũ vẫn có thể chứa lời gọi đến API mới. Nếu chỉ hạ phiên bản bytecode, ứng dụng có thể biên dịch thành công nhưng lỗi khi chạy trên JVM cũ do không tìm thấy phương thức hoặc lớp. --release giúp phát hiện nhiều lỗi API như vậy ngay ở bước biên dịch.

## 3. Phân biệt --release với -source và -target

Ba tùy chọn này giải quyết các phần khác nhau của bài toán:

| Tùy chọn | Kiểm soát cú pháp | Kiểm soát class file | Giới hạn API theo release |
|---|---:|---:|---:|
| -source N | Có | Không | Không |
| -target N | Không | Có | Không |
| --release N | Có | Có | Có |

**-source N** yêu cầu compiler chấp nhận cú pháp và tính năng ngôn ngữ của release N. Nó không tự giới hạn API nền tảng mà compiler nhìn thấy.

**-target N** yêu cầu compiler sinh class file cho release N. Nó không tự ngăn mã nguồn gọi API chỉ có ở JDK đang dùng để biên dịch.

**--release N** đồng bộ source, target và API Java SE của release N. Đây thường là lựa chọn trực tiếp nhất khi dự án cần cam kết tương thích với một phiên bản Java cụ thể.

Ví dụ, khi dùng JDK mới để biên dịch:

~~~bash
javac -source 9 -target 9 -d out src/com/acme/Main.java
~~~

Lệnh trên đặt cú pháp và định dạng bytecode theo Java 9, nhưng API có thể vẫn được tra cứu từ JDK đang cài. Mã nguồn vì vậy có nguy cơ tham chiếu API không tồn tại trên Java 9.

Cách đặt đầy đủ hơn:

~~~bash
javac --release 9 -d out src/com/acme/Main.java
~~~

Không ghép --release với -source hoặc -target trong cùng một lần biên dịch. --release đã thiết lập cả hai giá trị này và compiler không cho phép dùng chúng như các lựa chọn độc lập song song.

## 4. Ví dụ module Java 9 với --release 9

Giả sử dự án có module tên com.acme.compat:

~~~text
src/
└── com.acme.compat/
    ├── module-info.java
    └── com/
        └── acme/
            └── compat/
                └── Main.java
~~~

**Module descriptor — src/com.acme.compat/module-info.java:**

~~~java
module com.acme.compat {
    exports com.acme.compat;
}
~~~

**Class sử dụng API Java 9 — src/com.acme.compat/com/acme/compat/Main.java:**

~~~java
package com.acme.compat;

import java.util.List;

public class Main {
    public static void main(String[] args) {
        List<String> labels = List.of("Java", "9");
        System.out.println(String.join(" ", labels));
    }
}
~~~

Phương thức **List.of(...)** được bổ sung trong Java 9. Biên dịch module bằng compiler JDK 9 trở lên, chọn release 9:

**PowerShell:**

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
javac --release 9 --module-source-path src -d out -m com.acme.compat
~~~

**Bash:**

~~~bash
mkdir -p out
javac --release 9 --module-source-path src -d out -m com.acme.compat
~~~

Chạy module bằng Java 9 hoặc JDK mới hơn:

~~~bash
java --module-path out -m com.acme.compat/com.acme.compat.Main
~~~

Kết quả:

~~~text
Java 9
~~~

Ví dụ này đã được biên dịch bằng OpenJDK 24 với --release 9. Cả Main.class và module-info.class đều có major version 53, đúng định dạng class file của Java 9.

## 5. Kiểm tra phiên bản class file được sinh ra

Có thể kiểm tra bytecode sau khi biên dịch bằng javap:

~~~bash
javap -verbose -classpath out/com.acme.compat com.acme.compat.Main
~~~

Trong kết quả, tìm dòng:

~~~text
major version: 53
~~~

Một số major version thường gặp:

| Java release | Class-file major version |
|---|---:|
| Java 8 | 52 |
| Java 9 | 53 |
| Java 10 | 54 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |
| Java 24 | 68 |

Bảng này giúp kiểm tra định dạng bytecode mà compiler tạo ra. Tuy nhiên, chỉ nhìn major version chưa đủ để chứng minh ứng dụng tương thích: class file có thể vẫn tham chiếu API mới hoặc phụ thuộc vào thư viện bên ngoài có yêu cầu runtime cao hơn.

Với module, có thể kiểm tra cả module descriptor:

~~~bash
javap -verbose out/com.acme.compat/module-info.class
~~~

Nếu biên dịch bằng --release 9, module-info.class cũng được tạo theo định dạng Java 9.

## 6. --release giới hạn API theo phiên bản đích

Đây là khác biệt quan trọng giữa --release và việc chỉ đặt source/target.

**List.of** có từ Java 9. Đoạn mã sau biên dịch được với release 9:

~~~java
import java.util.List;

public class Main {
    public static void main(String[] args) {
        System.out.println(List.of("A", "B"));
    }
}
~~~

Nếu đổi sang release 8:

~~~bash
javac --release 8 -d out8 src/Main.java
~~~

Compiler báo không tìm thấy phương thức of trên interface List, bởi API Java 8 chưa có phương thức này.

Ngược lại, API **String.join(...)** đã có từ Java 8:

~~~java
public class LegacyApi {
    public static void main(String[] args) {
        System.out.println(String.join("-", "Java", "8"));
    }
}
~~~

Đoạn mã này biên dịch thành công với:

~~~bash
javac --release 8 -d out8 src/LegacyApi.java
~~~

Ví dụ trên OpenJDK 24 xác nhận:

- List.of biên dịch được với --release 9.
- Cùng lời gọi List.of bị từ chối với --release 8.
- String.join biên dịch được với --release 8.
- --release 25 bị từ chối vì nằm ngoài tập release JDK 24 hỗ trợ.

Khi compiler phát hiện API không thuộc release đích, hãy thay bằng API có từ release đó hoặc nâng phiên bản đích nếu yêu cầu sản phẩm cho phép.

## 7. Chọn release cho dự án có module-info.java

Module system được giới thiệu trong Java 9. Do đó:

- Module descriptor module-info.java chỉ phù hợp khi release đích từ Java 9 trở lên.
- Dự án cần chạy trên Java 8 phải cung cấp đầu ra không phụ thuộc vào module system Java 9; không thể đưa module-info.class vào một chương trình Java 8 như một module Java chuẩn.
- Nếu dự án hỗ trợ cả Java 8 và Java 9+, cần thiết kế cách đóng gói riêng cho hai mức tương thích, ví dụ artifact hoặc cấu trúc build phù hợp.

Biên dịch module nhắm Java 9:

~~~bash
javac --release 9 --module-source-path src -d out -m com.acme.compat
~~~

Biên dịch code không dùng module system nhắm Java 8:

~~~bash
javac --release 8 -d out8 src/com/acme/compat/LegacyMain.java
~~~

Không chọn release 8 cho một lần biên dịch module có module-info.java rồi kỳ vọng compiler tự bỏ descriptor. Hãy tách đúng source set hoặc module phù hợp với từng mục tiêu.

## 8. Các giới hạn cần biết khi chọn phiên bản đích

--release giúp compiler kiểm tra tính tương thích của source với Java SE release được chọn, nhưng không giải quyết mọi vấn đề triển khai.

**Thư viện bên ngoài**

Compiler kiểm tra API Java SE theo release đích. Nó không đảm bảo mọi thư viện bên thứ ba trên classpath hoặc module path đều tương thích với runtime đích. Một dependency có thể được biên dịch cho Java 17 dù ứng dụng chính được biên dịch với --release 9.

Hãy kiểm tra yêu cầu Java tối thiểu của dependency và bytecode của các artifact được phân phối cùng ứng dụng.

**Runtime thực tế**

Biên dịch với --release 9 không cài đặt Java 9 và không tạo runtime image. Nó chỉ tạo đầu ra tương thích với release đích ở phạm vi compiler kiểm soát. Hãy kiểm thử ứng dụng trên JVM tối thiểu mà sản phẩm cam kết hỗ trợ.

**API nội bộ của JDK**

Không xây dựng tương thích dựa trên các package nội bộ như jdk.internal.* hoặc sun.*. Những API này không thuộc hợp đồng Java SE ổn định và có thể thay đổi hoặc bị đóng quyền truy cập giữa các JDK.

**Tính năng preview**

Tính năng preview gắn với phiên bản JDK cụ thể. --enable-preview không phải cách để đưa một tính năng preview của JDK mới vào chương trình chạy trên một release cũ. Nếu dùng preview, phải tuân thủ yêu cầu compiler/runtime của đúng phiên bản phát hành tính năng đó.

**Tùy chọn compiler khác**

--release thiết lập source, target và API view. Không dùng đồng thời --source hoặc --target; cũng cần xem trợ giúp của javac khi phối hợp với tùy chọn thay thế system modules hoặc các tùy chọn can thiệp vào module graph.

## 9. Cấu hình build tool theo cùng một release

Nếu dự án dùng build tool, hãy bảo đảm cấu hình của build tool thực sự truyền release mục tiêu đến compiler.

Với Maven Compiler Plugin hiện đại, có thể đặt property:

~~~xml
<properties>
    <maven.compiler.release>9</maven.compiler.release>
</properties>
~~~

Với Gradle, cấu hình JavaCompile task:

~~~kotlin
tasks.withType<JavaCompile>().configureEach {
    options.release = 9
}
~~~

Cú pháp và khả năng hỗ trợ phụ thuộc phiên bản plugin hoặc Gradle đang dùng. Kiểm tra log compiler để chắc chắn build thật sự gọi javac với --release mong muốn.

Không chỉ đặt sourceCompatibility và targetCompatibility rồi mặc định rằng API surface cũng được giới hạn. Với Gradle, options.release là thiết lập tương ứng trực tiếp với javac --release.

## 10. Quy trình chọn phiên bản đích

Trước khi quyết định release, xác định runtime thấp nhất mà sản phẩm phải hỗ trợ. Sau đó kiểm tra compiler và dependency:

1. Xác định phiên bản Java tối thiểu mà môi trường triển khai sẽ chạy.
2. Chọn đúng release tương ứng, ví dụ 9 nếu sản phẩm cần chạy từ Java 9.
3. Chạy javac --help để xác nhận compiler hiện tại hỗ trợ release đó.
4. Dùng --release N để biên dịch source, bytecode và API theo cùng một mốc.
5. Kiểm tra major version bằng javap -verbose nếu cần xác minh bytecode.
6. Kiểm tra thư viện ngoài và plugin có yêu cầu Java tối thiểu phù hợp.
7. Chạy test trên JVM thấp nhất đã cam kết hỗ trợ, không chỉ trên JDK dùng để build.
8. Nếu release không được hỗ trợ, dùng compiler JDK phù hợp hoặc điều chỉnh mục tiêu tương thích theo yêu cầu sản phẩm.

Một ví dụ lựa chọn:

~~~text
Runtime tối thiểu cần hỗ trợ: Java 9
Compiler hiện tại: JDK 24
javac --help: release 9 nằm trong danh sách hỗ trợ
Lệnh build: javac --release 9 ...
Kiểm tra bytecode: major version 53
Kiểm thử: chạy trên Java 9 và các runtime mới hơn
~~~

## 11. Lỗi thường gặp và cách xử lý

**release version ... not supported**

Giá trị được chọn không có trong tập compiler hỗ trợ. Xem javac --help; nếu cần target release mới hơn, nâng JDK compiler.

**Mã nguồn dùng cú pháp mới hơn release đích**

Ví dụ dùng cú pháp var khi chọn release 9. Hãy thay bằng cú pháp được release đích hỗ trợ hoặc nâng release nếu sản phẩm cho phép.

**Không tìm thấy phương thức dù JDK đang cài có phương thức đó**

Compiler đang kiểm tra API của release đích. Nếu phương thức được thêm sau release đó, lỗi là đúng. Chọn API cũ hơn hoặc nâng release.

**Class file có major version phù hợp nhưng ứng dụng vẫn lỗi runtime**

Kiểm tra lời gọi API, dependency, reflection, service provider và module descriptor. Class-file version chỉ xác nhận định dạng bytecode.

**Dùng --release 8 cho source có module-info.java**

Module system cần Java 9 trở lên. Tách source set hoặc artifact cho Java 8 và Java 9+.

**Kết hợp --release với -source hoặc -target**

Bỏ hai tùy chọn riêng lẻ. --release đã đồng bộ source và target cho release đã chọn.

**Máy build và máy chạy khác nhau**

Đặt release theo runtime tối thiểu mà sản phẩm hỗ trợ, sau đó kiểm thử trên chính runtime đó. Không lấy phiên bản JDK cài trên máy build làm mặc định cho phiên bản đích.

## 12. Checklist trước khi phát hành

- [ ] Đã xác định phiên bản Java tối thiểu cần hỗ trợ.
- [ ] Đã kiểm tra javac --help và xác nhận release đích nằm trong danh sách supported releases.
- [ ] Đang dùng --release N thay vì chỉ kết hợp -source và -target.
- [ ] Source không dùng cú pháp hoặc API mới hơn release đích.
- [ ] Nếu release dưới 9, source set không chứa module-info.java.
- [ ] Đã kiểm tra major version của class file khi cần.
- [ ] Tất cả dependency và plugin có runtime requirement tương thích.
- [ ] Đã chạy test trên JVM tối thiểu được hỗ trợ.
- [ ] Build tool và CI dùng cùng release mục tiêu.

Chọn phiên bản đích đúng nghĩa là giữ cho cú pháp, bytecode và API cùng nằm trong giới hạn của một Java release. Dùng --release với giá trị được compiler hỗ trợ giúp phát hiện lỗi tương thích ngay trong build và tạo ra cam kết rõ ràng hơn cho runtime mà ứng dụng cần phục vụ.