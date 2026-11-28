# Phân biệt JDK dùng để build, mức --release và runtime được phân phối

## 1. Ba thành phần có vai trò khác nhau

Khi xây dựng và phát hành một ứng dụng Java, cần phân biệt ba lựa chọn thường bị nhầm lẫn:

1. **JDK dùng để build:** bộ công cụ chạy trình biên dịch và các công cụ build như `javac`, `jdeps`, `jlink`, `jpackage`.
2. **Mức `--release`:** phiên bản nền tảng Java mà mã nguồn được biên dịch để tương thích, gồm cú pháp ngôn ngữ, định dạng bytecode và tập API Java SE được phép sử dụng.
3. **Runtime được phân phối:** môi trường Java thực sự chạy ứng dụng trên máy người dùng. Runtime có thể là JDK cài sẵn hoặc runtime image tùy chỉnh được đóng gói cùng ứng dụng.

Ba lựa chọn này liên quan nhưng không đồng nhất. Ví dụ, có thể dùng JDK 25 để build mã nguồn tương thích Java 16 bằng `javac --release 16`, rồi chạy ứng dụng trên runtime Java 25. Ứng dụng được biên dịch cho nền tảng Java 16, còn runtime đi kèm vẫn là Java 25.

## 2. JDK dùng để build quyết định công cụ nào thực hiện quá trình build

JDK là bộ công cụ dành cho phát triển Java. Tùy phiên bản và bản phân phối, JDK cung cấp các công cụ như:

- `javac`: biên dịch mã nguồn Java thành bytecode.
- `jar`: tạo và thao tác với file JAR.
- `jdeps`: phân tích phụ thuộc giữa các lớp và module.
- `jlink`: liên kết các module để tạo runtime image.
- `jpackage`: tạo application image hoặc installer native.

JDK dùng để build được chọn qua môi trường build, cấu hình toolchain hoặc đường dẫn công cụ. Kiểm tra phiên bản đang được gọi:

~~~powershell
javac --version
java --version
where.exe javac
where.exe java
~~~

`javac` và `java` có thể đến từ hai thư mục JDK khác nhau nếu `PATH` được cấu hình không nhất quán. Trong pipeline, nên cố định JDK/toolchain rõ ràng để build có thể lặp lại.

JDK dùng để build ảnh hưởng đến:

- Phiên bản compiler và các tùy chọn compiler có sẵn.
- Các công cụ phụ trợ như `jlink`, `jpackage`, `jdeps`.
- Module và API mà compiler có thể nhìn thấy nếu không giới hạn phiên bản đích.
- Phiên bản JDK được các plugin, annotation processor và công cụ build sử dụng.

Chọn một JDK mới để build không có nghĩa ứng dụng bắt buộc phải chạy trên đúng phiên bản JDK đó. Mức tương thích cần được xác định riêng bằng tùy chọn biên dịch và runtime mục tiêu.

## 3. `--release` kiểm soát cú pháp, bytecode và API Java SE

Tùy chọn `javac --release N` yêu cầu compiler biên dịch mã nguồn theo nền tảng Java release `N`. Về thực tế, nó kết hợp ba ràng buộc:

- Chấp nhận cú pháp và quy tắc ngôn ngữ của release được chọn.
- Sinh bytecode có phiên bản class file tương ứng.
- Giới hạn các API Java SE được tham chiếu ở mức có trong release đó.

Ví dụ, dùng JDK mới để biên dịch mã tương thích Java 16:

~~~powershell
javac --release 16 -d out src\com\example\Main.java
~~~

Với Java 16, class file có major version 60. Runtime Java 16 trở lên có thể hiểu định dạng bytecode này, miễn là các dependency và API mà ứng dụng cần đều tương thích.

Điểm quan trọng là `--release 16` ngăn mã nguồn vô tình gọi API Java SE được bổ sung sau Java 16. Nếu compiler mới nhìn thấy một phương thức chỉ có từ Java 21, mã tham chiếu đến phương thức đó sẽ không biên dịch khi dùng `--release 16`.

`--release` không đóng gói runtime, không cài Java cho máy đích và cũng không tự chọn JDK để chạy ứng dụng. Nó chỉ kiểm soát mục tiêu biên dịch.

## 4. Vì sao nên dùng `--release` thay cho chỉ đặt source và target?

Các tùy chọn `-source` và `-target` riêng lẻ kiểm soát mức cú pháp và định dạng bytecode, nhưng không tự giới hạn đầy đủ API nền tảng mà compiler mới nhìn thấy.

Ví dụ, nếu chỉ dùng:

~~~powershell
javac -source 16 -target 16 -d out src\com\example\Main.java
~~~

compiler mới có thể chấp nhận lời gọi một API được thêm vào JDK mới hơn, dù bytecode được tạo hướng tới Java 16. Khi chạy trên Java 16, ứng dụng có thể gặp `NoSuchMethodError` hoặc `NoClassDefFoundError`.

Với:

~~~powershell
javac --release 16 -d out src\com\example\Main.java
~~~

compiler giới hạn cả API Java SE theo release 16. Đây là cách phù hợp hơn khi cần biên dịch chéo cho một phiên bản Java cụ thể.

Trong build mới, hãy cấu hình release rõ ràng thay vì chỉ đặt `source` và `target`. `--release` có từ JDK 9 và vẫn là lựa chọn hiện hành cho compiler Java.

## 5. Runtime được phân phối quyết định môi trường thực thi

Sau khi biên dịch, ứng dụng cần một Java runtime để thực thi. Runtime có thể được cung cấp theo các cách:

- Máy người dùng đã cài một Java runtime phù hợp, thường là runtime đi cùng bản phân phối JDK.
- Nhà phát hành cung cấp một runtime image được tạo bằng `jlink`.
- `jpackage` đóng gói ứng dụng cùng runtime image để người dùng chạy launcher của ứng dụng.

Runtime phải hiểu được phiên bản bytecode của ứng dụng và cung cấp các API, module cùng dependency mà ứng dụng cần.

Ví dụ:

| JDK dùng để build | Mức biên dịch | Runtime chạy ứng dụng | Kết quả |
| --- | --- | --- | --- |
| JDK 25 | `--release 16` | Java 25 | Có thể chạy; runtime mới hơn mức bytecode |
| JDK 25 | `--release 16` | Java 21 | Có thể chạy nếu dependency và API tương thích |
| JDK 25 | `--release 16` | Java 16 | Về mặt tương thích nền tảng có thể chạy, nhưng Java 16 đã hết vòng đời hỗ trợ |
| JDK 25 | Mặc định Java 25 | Java 16 | Không chạy được; runtime cũ không hiểu bytecode mới hơn |

Một runtime mới thường có thể chạy bytecode cũ hơn, nhưng điều đó không bảo đảm mọi hành vi của ứng dụng giống hệt trên mọi JDK. Cần kiểm thử với runtime thực tế sẽ phân phối.

## 6. `--release 16` không tạo ra runtime Java 16

Đây là điểm cần nhớ khi kết hợp `javac`, `jlink` và `jpackage`.

Giả sử compiler JDK 25 tạo bytecode Java 16:

~~~powershell
javac --release 16 -d out src\com\example\Main.java
~~~

Sau đó dùng `jlink` từ JDK 25:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.example.app --output build\runtime
~~~

Runtime image được tạo là runtime thuộc JDK 25, vì các module hệ thống lấy từ bộ `jmods` của JDK 25. `--release 16` ở bước biên dịch không làm `jlink` hạ runtime xuống Java 16.

Tương tự, nếu chạy `jpackage` từ JDK 25 mà không truyền `--runtime-image`, runtime được tạo trong quy trình đóng gói sẽ dựa trên JDK dùng cho công cụ đó. Nếu truyền `--runtime-image`, `jpackage` sử dụng runtime image được chỉ định.

Vì vậy:

- `javac --release 16`: chọn nền tảng biên dịch tương thích Java 16.
- `jlink` từ JDK 25: tạo runtime image Java 25.
- `jpackage` từ JDK 25: đóng gói ứng dụng và runtime được tạo/chỉ định trong quy trình đó.

Không có quan hệ tự động nào khiến `--release 16` buộc `jlink` hoặc `jpackage` phải tạo runtime Java 16.

## 7. Ví dụ một pipeline: build target 16, phân phối runtime mới hơn

Giả sử ứng dụng module hóa có cấu trúc:

~~~text
src/
  com.example.notes/
    module-info.java
    com/
      example/
        notes/
          Main.java
~~~

Module descriptor:

~~~java
module com.example.notes {
    requires java.logging;
}
~~~

Lớp chính:

~~~java
package com.example.notes;

import java.util.logging.Logger;

public class Main {
    public static void main(String[] args) {
        Logger.getLogger(Main.class.getName()).info("Notes application started");
    }
}
~~~

**Bước 1 — chọn JDK build.** Pipeline dùng JDK 25 và kiểm tra toolchain:

~~~powershell
javac --version
java --version
~~~

**Bước 2 — biên dịch theo nền tảng Java 16.**

~~~powershell
javac --release 16 --module-source-path src -d out -m com.example.notes
~~~

Compiler JDK 25 kiểm tra cú pháp và API theo release 16, đồng thời tạo class file tương thích Java 16.

**Bước 3 — chạy thử bằng runtime mục tiêu.** Nếu quyết định phân phối runtime Java 25, chạy thử module trên JDK 25:

~~~powershell
java --module-path out -m com.example.notes/com.example.notes.Main
~~~

**Bước 4 — tạo runtime image Java 25.** Dùng JDK 25 để tạo runtime image có module ứng dụng và module JDK cần thiết:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;out" --add-modules com.example.notes --output build\runtime
~~~

**Bước 5 — đóng gói application image với runtime đã tạo.**

~~~powershell
jpackage --type app-image --name NotesApp --module-path out --module com.example.notes/com.example.notes.Main --runtime-image build\runtime --dest dist
~~~

Gói được tạo có runtime Java 25. Ứng dụng vẫn được biên dịch theo API và bytecode Java 16. Đây là lựa chọn hữu ích khi muốn duy trì mức tương thích mã nguồn cũ nhưng phân phối một runtime còn được cập nhật hỗ trợ.

## 8. Chọn runtime theo chính sách hỗ trợ, không chỉ theo mức bytecode

Java 16 là bản phát hành không phải LTS và đã kết thúc vòng đời hỗ trợ. Vì vậy, dù `--release 16` vẫn hữu ích để giữ tương thích với nền tảng Java 16, không nên mặc định chọn runtime Java 16 cho một hệ thống production mới.

Một hướng triển khai hiện đại là:

- Giữ `--release 16` nếu phải hỗ trợ một thư viện, plugin hoặc môi trường triển khai có yêu cầu tương thích Java 16.
- Phân phối runtime từ một bản JDK LTS còn được nhà cung cấp hỗ trợ, chẳng hạn Java 21 hoặc Java 25, theo chính sách của tổ chức.
- Kiểm thử trên đúng runtime và nền tảng hệ điều hành/CPU dự kiến.
- Lập kế hoạch nâng mức `--release` khi không còn cần tương thích với Java 16.

Nếu bắt buộc chạy trên runtime Java 16 do ràng buộc hệ thống cũ, cần ghi nhận rủi ro vòng đời hỗ trợ và có kế hoạch chuyển đổi. Không nên nhầm việc bytecode tương thích với việc runtime còn được cập nhật bảo mật.

## 9. Các giới hạn của `--release`

`--release` rất hữu ích nhưng không phải công cụ xác nhận toàn bộ khả năng chạy của ứng dụng:

- **Thư viện bên thứ ba:** compiler kiểm soát API nền tảng Java SE, nhưng không bảo đảm mọi thư viện ngoài tương thích với runtime mục tiêu. Cần kiểm tra phiên bản bytecode và yêu cầu JDK của dependency.
- **Reflection:** lời gọi lớp/phương thức qua tên chuỗi có thể không được compiler kiểm tra như lời gọi trực tiếp.
- **JNI và thư viện native:** khả năng tương thích còn phụ thuộc hệ điều hành, kiến trúc CPU và ABI.
- **Hành vi runtime:** khác biệt về GC, bảo mật, TLS, charset, locale hoặc mặc định hệ thống có thể ảnh hưởng ứng dụng khi đổi JDK.
- **Công cụ build và annotation processor:** chúng chạy trong môi trường JDK build và có thể có yêu cầu phiên bản riêng.

Có thể dùng `jdeps` để phân tích phụ thuộc tĩnh và tìm một số tham chiếu tới API/module không phù hợp. Tuy nhiên, vẫn phải chạy test tích hợp và kiểm thử application image trên runtime phân phối.

## 10. Cấu hình build tool một cách tường minh

Với Maven hoặc Gradle, nên khai báo rõ hai lựa chọn riêng:

1. JDK/toolchain dùng để chạy compiler và các tác vụ build.
2. Release mục tiêu truyền cho compiler.

Không nên dựa vào JDK tình cờ đứng đầu `PATH` trên máy lập trình viên. Toolchain tường minh giúp máy cá nhân và CI dùng cùng phiên bản compiler. Cấu hình release giúp tránh vô tình sử dụng cú pháp hoặc API mới hơn nền tảng tương thích đã chọn.

Ngoài compile, hãy xác định runtime dùng cho test và runtime dùng cho production. Chúng có thể giống nhau, nhưng không tự động giống chỉ vì compiler đã dùng `--release`.

## 11. Bảng phân biệt nhanh

| Thành phần | Câu hỏi nó trả lời | Ví dụ |
| --- | --- | --- |
| JDK build/toolchain | Dùng compiler và công cụ nào để build? | JDK 25 |
| `--release` | Mã được biên dịch để tương thích với Java nào? | `--release 16` |
| Runtime kiểm thử | Ứng dụng được chạy và kiểm thử trên JDK nào? | Java 25 |
| Runtime phân phối | Người dùng nhận được bộ chạy Java nào? | Runtime image tạo từ JDK 25 |
| `jlink` | Tạo runtime image gồm module nào? | `--add-modules com.example.notes` |
| `jpackage` | Đóng gói ứng dụng thành loại gói nào và dùng runtime nào? | `--type app-image --runtime-image build/runtime` |

**Ghi nhớ:** JDK build là bộ công cụ tạo ứng dụng; `--release` xác định mức ngôn ngữ, bytecode và API Java SE mà compiler cho phép; runtime được phân phối là môi trường thực sự chạy ứng dụng. `--release 16` không tạo runtime Java 16. Hãy chọn runtime còn được hỗ trợ, kiểm tra dependency và thử gói cuối trên đúng môi trường triển khai.
