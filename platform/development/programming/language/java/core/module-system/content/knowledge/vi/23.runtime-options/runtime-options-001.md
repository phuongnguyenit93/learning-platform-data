# --add-reads thêm readability tạm thời

## 1. Readability trong Java Module System

Trong Java Platform Module System (JPMS), mỗi named module có một tập module mà nó **reads** (đọc được). Quan hệ readability quyết định mã trong module hiện tại có thể tham chiếu đến các kiểu public được module khác xuất ra hay không.

Thông thường, quan hệ này được khai báo trong **module-info.java** bằng **requires**:

~~~java
module com.example.app {
    requires com.example.logging;
}
~~~

Khai báo trên tạo phụ thuộc rõ ràng giữa **com.example.app** và **com.example.logging**. Khi build và chạy, hệ thống module phải phân giải được module logging cùng các phụ thuộc bắt buộc của nó.

Tuy nhiên, có những tình huống cần bổ sung readability tạm thời mà không sửa module descriptor, chẳng hạn:

- Đang chuyển một ứng dụng từ classpath sang named module.
- Cần kết nối một named module với thư viện cũ nằm trên classpath.
- Đang kiểm thử hoặc chẩn đoán một module graph.
- Một plugin hoặc module được chọn theo cấu hình runtime, nên phụ thuộc không thể ghi trực tiếp trong descriptor của module chính.

Tùy chọn **--add-reads** cho phép thêm một cạnh readability vào module graph của lần biên dịch hoặc lần khởi chạy. Đây là điều chỉnh qua dòng lệnh, không ghi lại **module-info.java** và không biến phụ thuộc tạm thời thành hợp đồng module lâu dài.

## 2. Cú pháp của --add-reads

Cú pháp tổng quát:

~~~text
--add-reads <module>=<target-module>(,<target-module>)*
~~~

Trong đó:

- **module** là named module cần được bổ sung quyền đọc.
- **target-module** là module mà module nguồn sẽ đọc được.
- Có thể chỉ định nhiều module đích, phân tách bằng dấu phẩy.
- **ALL-UNNAMED** là tên đặc biệt đại diện cho tất cả unnamed module, thường là các class và JAR trên classpath.

Ví dụ:

~~~bash
java --add-reads com.example.app=com.example.logging \
     --module-path mods \
     -m com.example.app/com.example.app.Main
~~~

Lệnh này bổ sung quan hệ để **com.example.app** đọc được **com.example.logging** trong lần chạy hiện tại.

Có thể thêm nhiều module đích:

~~~bash
java --add-reads com.example.app=com.example.logging,com.example.metrics \
     --module-path mods \
     -m com.example.app/com.example.app.Main
~~~

Cần bảo đảm các module đích có thể được tìm thấy và phân giải trong module graph. Nếu một module chưa được đưa vào tập module gốc cần phân giải, có thể cần chỉ định thêm **--add-modules**:

~~~bash
java --module-path mods \
     --add-modules com.example.logging \
     --add-reads com.example.app=com.example.logging \
     -m com.example.app/com.example.app.Main
~~~

**--add-modules** đưa module vào tập module cần phân giải; **--add-reads** bổ sung quan hệ readability từ module nguồn đến module đích. Hai tùy chọn giải quyết hai việc khác nhau.

## 3. Dùng --add-reads với ALL-UNNAMED

Các thư viện cũ thường được đặt trên classpath và thuộc unnamed module. Một named module không tự động đọc unnamed module. Khi cần named module sử dụng API public của thư viện classpath trong giai đoạn chuyển đổi, có thể thêm readability đến **ALL-UNNAMED**.

Giả sử thư viện cũ có class:

~~~java
package com.legacy.codec;

public class LegacyEncoder {
    public String encode(String value) {
        return "encoded:" + value;
    }
}
~~~

JAR chứa class này nằm trong thư mục **legacy-libs**. Ứng dụng modular có mã:

~~~java
package com.example.app;

import com.legacy.codec.LegacyEncoder;

public class Main {
    public static void main(String[] args) {
        LegacyEncoder encoder = new LegacyEncoder();
        System.out.println(encoder.encode("hello"));
    }
}
~~~

Module descriptor của ứng dụng:

~~~java
module com.example.app {
}
~~~

Để biên dịch module và cho nó đọc thư viện classpath, có thể dùng:

~~~bash
javac \
  --class-path "legacy-libs/*" \
  --add-reads com.example.app=ALL-UNNAMED \
  --module-source-path src \
  -d out \
  -m com.example.app
~~~

Khi chạy, cần bổ sung readability tương ứng cho runtime:

~~~bash
java \
  --module-path out \
  --class-path "legacy-libs/*" \
  --add-reads com.example.app=ALL-UNNAMED \
  -m com.example.app/com.example.app.Main
~~~

Ví dụ này minh họa một cầu nối tạm thời giữa named module và thư viện trên classpath. **ALL-UNNAMED** bao gồm tất cả classpath JAR thuộc unnamed module trong môi trường chạy đó; nó không chỉ giới hạn ở một JAR cụ thể.

Do phạm vi rộng, hãy cân nhắc chuyển thư viện cũ thành named module hoặc đưa phụ thuộc vào module descriptor khi kiến trúc đã ổn định. Nếu ứng dụng dùng API của thư viện trong thời gian dài, một khai báo **requires** tường minh trên module path thường dễ quản lý và kiểm soát hơn.

## 4. Dùng --add-reads khi biên dịch

javac hỗ trợ **--add-reads** để điều chỉnh readability trong quá trình biên dịch. Điều này có thể hữu ích khi đang kiểm thử một thay đổi module hoặc khi phải tích hợp tạm thời với một thư viện chưa có module descriptor phù hợp.

Ví dụ module **com.example.app** cần đọc module **com.example.legacy** trong thư mục **mods**:

~~~bash
javac \
  --module-path mods \
  --add-modules com.example.legacy \
  --add-reads com.example.app=com.example.legacy \
  --module-source-path src \
  -d out \
  -m com.example.app
~~~

Trong ví dụ:

- **--module-path mods** cung cấp module legacy.
- **--add-modules com.example.legacy** yêu cầu đưa module legacy vào tập module gốc cần phân giải.
- **--add-reads com.example.app=com.example.legacy** cho phép module app đọc module legacy trong lượt biên dịch.
- **-m com.example.app** chọn module app để biên dịch.

Nếu mã nguồn thuộc named module và trực tiếp sử dụng API của legacy, việc build chỉ thành công nhờ tùy chọn dòng lệnh này chưa đủ để ứng dụng chạy đúng. Khi chạy, phải có quan hệ readability tương ứng trong runtime module graph.

Ví dụ lệnh chạy:

~~~bash
java \
  --module-path "out:mods" \
  --add-modules com.example.legacy \
  --add-reads com.example.app=com.example.legacy \
  -m com.example.app/com.example.app.Main
~~~

Trên Windows, thay dấu phân cách module path bằng dấu chấm phẩy:

~~~powershell
java --module-path "out;mods" --add-modules com.example.legacy --add-reads com.example.app=com.example.legacy -m com.example.app/com.example.app.Main
~~~

Cần cấu hình cả giai đoạn biên dịch và runtime. Tùy chọn javac không tự được lưu vào module descriptor đã biên dịch để JVM tự áp dụng ở lần chạy sau.

## 5. --add-reads không thay thế requires

Giả sử module app cần sử dụng API của module logging. Có hai cách mô tả quan hệ:

**Cách lâu dài trong module descriptor:**

~~~java
module com.example.app {
    requires com.example.logging;
}
~~~

**Cách bổ sung tạm thời trên dòng lệnh:**

~~~bash
java --add-reads com.example.app=com.example.logging \
     --module-path mods \
     -m com.example.app/com.example.app.Main
~~~

Cả hai đều có thể tạo readability trong ngữ cảnh tương ứng, nhưng ý nghĩa quản lý khác nhau:

- **requires** là một phần của thiết kế module, được biên dịch vào module descriptor và đi cùng module khi phân phối.
- **--add-reads** là cấu hình bên ngoài, chỉ có hiệu lực trong lần biên dịch hoặc khởi chạy mà tùy chọn được truyền vào.

Nếu phụ thuộc là một phần ổn định của API hoặc implementation, nên khai báo **requires**. Dùng **--add-reads** khi cần can thiệp tạm thời, kiểm thử, tương thích ngược hoặc xử lý cấu hình runtime đặc biệt.

Đừng dùng **--add-reads** để che giấu module descriptor thiếu phụ thuộc trong sản phẩm đã modular hóa. Người khác có thể chạy cùng module mà không có tùy chọn đó và gặp lỗi readability.

## 6. Readability khác exports và opens

Một lỗi phổ biến là nhầm lẫn giữa việc module đọc được module khác và việc package của module đó có thể truy cập được.

Giả sử module **com.example.internal** chứa:

~~~java
module com.example.internal {
    // Không export package com.example.internal.api
}
~~~

Module app được bổ sung readability:

~~~bash
java --add-reads com.example.app=com.example.internal \
     --module-path mods \
     -m com.example.app/com.example.app.Main
~~~

Mặc dù app đọc được module internal, nó vẫn không thể truy cập các kiểu trong package chưa được module internal export.

Các cơ chế liên quan:

| Cơ chế | Điều khiển điều gì? |
|---|---|
| **requires** | Readability được khai báo trong descriptor |
| **--add-reads** | Readability bổ sung qua dòng lệnh |
| **exports** | Công khai package để module đọc có thể dùng kiểu public |
| **--add-exports** | Bổ sung quyền truy cập package public qua dòng lệnh |
| **opens** | Cho phép deep reflection vào package |
| **--add-opens** | Bổ sung quyền deep reflection qua dòng lệnh |
| **--add-modules** | Bổ sung module vào tập module gốc cần phân giải |

Ví dụ, để module app đọc module library và truy cập package public mà library export có điều kiện, cần xác định đúng cả quan hệ readability lẫn quy tắc export. Nếu mục tiêu là reflection sâu vào thành viên private, cần xem xét **opens** hoặc **--add-opens**.

Không phải lỗi truy cập nào cũng giải quyết được bằng **--add-reads**. Hãy đọc nội dung lỗi để phân biệt lỗi module không đọc, package chưa export và reflection bị đóng.

## 7. Phạm vi và giới hạn của --add-reads

**--add-reads** bổ sung quan hệ readability, nhưng không thực hiện các việc sau:

- Không thêm module hoặc JAR vào module path.
- Không tự phân giải module đích nếu module đó chưa được đưa vào graph.
- Không export package từ module đích.
- Không mở package cho deep reflection.
- Không sửa hoặc ghi lại **module-info.java**.
- Không tự động truyền cấu hình từ javac sang JVM.
- Không tải dependency từ mạng hoặc thay thế công cụ quản lý dependency.

Tùy chọn này cũng không làm thay đổi mã nguồn hoặc cấu trúc đóng gói của thư viện. Nếu module đích không tồn tại hoặc tên module sai, cần sửa module path hoặc tên module trước.

Với **ALL-UNNAMED**, hãy nhớ đây là pseudo-module đại diện cho unnamed module, không phải một module JAR có thể tìm thấy trên module path. Nó hữu ích trong tích hợp legacy classpath, nhưng có phạm vi rộng hơn một named module cụ thể.

## 8. Dùng --add-reads trong môi trường kiểm thử

Một ứng dụng có thể cần thêm readability chỉ trong một bài kiểm thử tích hợp. Khi đó, có thể truyền tùy chọn vào lệnh chạy test thay vì sửa descriptor của module chính.

Ví dụ chạy một module test hoặc ứng dụng với một module hỗ trợ:

~~~bash
java \
  --module-path "out:mods:test-mods" \
  --add-modules com.example.test.support \
  --add-reads com.example.app=com.example.test.support \
  -m com.example.test/com.example.test.Runner
~~~

Ví dụ này yêu cầu module **com.example.app** đọc module hỗ trợ trong module graph của lần chạy test. Tên module và module gốc cần được thay bằng cấu trúc thực tế của dự án.

Nếu một framework test dùng reflection sâu vào package của module ứng dụng, **--add-reads** chưa đủ. Cần cấu hình **--add-opens** cho đúng package và module framework, hoặc khai báo mở package phù hợp trong descriptor của cấu hình test.

Hãy giữ các tùy chọn mở rộng này trong cấu hình test riêng. Không đưa chúng vào lệnh chạy production nếu ứng dụng không cần.

## 9. Chẩn đoán lỗi readability

Khi gặp thông báo dạng:

~~~text
module com.example.app does not read module com.example.legacy
~~~

Có thể thực hiện các bước sau:

1. Xác định module nguồn được nêu trong lỗi.
2. Xác định module đích sở hữu class hoặc package mà mã đang sử dụng.
3. Kiểm tra module đích có mặt trên module path hay không.
4. Nếu phụ thuộc là chính thức, khai báo **requires** trong module descriptor.
5. Nếu chỉ cần điều chỉnh tạm thời, thử **--add-reads source=target** trong đúng lệnh javac hoặc java.
6. Nếu module đích chưa được phân giải, xem xét **--add-modules target**.
7. Nếu sau đó lỗi chuyển thành package không visible, kiểm tra **exports**.
8. Nếu lỗi xuất hiện khi reflection truy cập private member, kiểm tra **opens** hoặc **--add-opens**.

Có thể xem module descriptor bằng:

~~~bash
java --module-path mods --describe-module com.example.legacy
~~~

Và xem các module đang được nhận diện:

~~~bash
java --module-path mods --list-modules
~~~

Các lệnh này giúp xác nhận tên module và vị trí phân giải trước khi thay đổi cấu hình.

## 10. Quy trình sử dụng an toàn

Khi cần thêm readability tạm thời, hãy làm theo quy trình:

1. Xác định rõ module nào cần đọc module nào.
2. Kiểm tra module đích có thể được tìm thấy trên module path hoặc trong runtime.
3. Xác định lỗi thực sự là readability, exports hay deep reflection.
4. Truyền **--add-reads** vào đúng giai đoạn cần điều chỉnh: javac hoặc java.
5. Nếu module đích chưa được phân giải, cân nhắc **--add-modules**.
6. Kiểm thử cả compile và runtime vì cấu hình của hai giai đoạn độc lập.
7. Ghi lại lý do dùng tùy chọn và phạm vi module được mở rộng.
8. Khi phụ thuộc trở thành ổn định, chuyển sang khai báo **requires** phù hợp trong module descriptor.

## 11. Ghi nhớ

- **--add-reads source=target** bổ sung quan hệ readability từ module nguồn đến module đích.
- **ALL-UNNAMED** đại diện cho các class và JAR thuộc unnamed module trên classpath.
- Có thể dùng tùy chọn ở javac để biên dịch và ở java để chạy; hai cấu hình không tự đồng bộ.
- Module đích phải được tìm thấy và phân giải; **--add-modules** có thể cần thiết để bổ sung module vào graph.
- Readability không đồng nghĩa với package visibility hoặc deep reflection.
- **--add-reads** là điều chỉnh qua dòng lệnh, không thay thế khai báo phụ thuộc chính thức bằng **requires**.

Hãy dùng **--add-reads** như một công cụ điều chỉnh module graph có chủ đích cho migration, test hoặc tích hợp legacy. Với phụ thuộc ổn định của một named module, ghi rõ **requires** trong module descriptor giúp build và runtime nhất quán hơn.
