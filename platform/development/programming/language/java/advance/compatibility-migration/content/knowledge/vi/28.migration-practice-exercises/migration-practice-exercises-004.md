# Tạo thư viện mới làm hỏng artifact bên sử dụng cũ

Trong **Java Advance Compatibility Migration**, một lỗi khó phát hiện là **thư viện mới biên dịch thành công, ứng dụng mới biên dịch thành công, nhưng artifact của bên sử dụng đã biên dịch từ trước lại hỏng khi chạy**. Nguồn lỗi là **binary compatibility**: bytecode của consumer vẫn chứa lời gọi tới tên class, tên method và method descriptor cũ, còn thư viện mới đã bỏ hoặc thay đổi phần API tương ứng.

Bài thực hành này dựng một hệ thống nhỏ gồm **thư viện** `catalog-core` và **bên sử dụng** `legacy-client`. Ở phiên bản thư viện v1, method `formatPrice(int)` tồn tại. Sang v2, tác giả thư viện đổi method đó thành `formatPrice(long)` với ý định “mở rộng kiểu số, chắc sẽ tương thích”. Mã nguồn client cũ **vẫn có thể biên dịch lại** với v2, vì Java cho phép chuyển `int` sang `long`. Nhưng file `legacy-client.jar` được biên dịch với v1 vẫn gọi descriptor `(I)Ljava/lang/String;`, dẫn tới `NoSuchMethodError` khi chạy cùng v2.

Từ một ca lỗi có chủ đích, bạn sẽ học cách tái hiện, điều tra bytecode, phân biệt tương thích nguồn với tương thích nhị phân, sửa bằng **compatibility bridge**, rồi thiết kế regression gate để phát hiện vấn đề trước khi phát hành thư viện.

> **Phạm vi:** Đây là bài học tự chứa. Những dòng lệnh và kết quả trong bài là **hướng dẫn/mô phỏng dự kiến**, không phải báo cáo rằng chúng đã được chạy trên một môi trường thực tế. Bài sử dụng Java 17+ cho cú pháp `jar --create` và tùy chọn `javac --release 17`. Không cần Maven, Gradle, database hay mạng để thực hiện phần thực hành chính.

## 1. Mục tiêu sau bài thực hành

Sau khi hoàn thành, bạn có thể:

1. Mô tả khác biệt giữa **source compatibility**, **binary compatibility** và **behavioral compatibility**.
2. Tạo hai artifact độc lập: một JAR thư viện và một JAR consumer.
3. Giữ nguyên consumer JAR đã biên dịch, thay thư viện lúc runtime để tái hiện lỗi linkage.
4. Hiểu tại sao method `formatPrice(int)` và `formatPrice(long)` khác nhau dù lời gọi trong source nhìn không thay đổi.
5. Dùng `javap` quan sát method descriptor mà JVM thực sự cần.
6. Phân biệt `NoSuchMethodError` với lỗi compile, `ClassNotFoundException` và `NoClassDefFoundError`.
7. Sửa v2 bằng bridge/overload giữ API cũ, **không rebuild artifact consumer cũ**.
8. Đề xuất các phép kiểm source, binary và runtime cho một thư viện công bố hỗ trợ consumer đã phát hành.

## 2. Bối cảnh thực tế

Hãy hình dung hệ thống gồm ba nhóm:

~~~text
Nhóm thư viện
  catalog-core v1
       |
       +--> phát hành catalog-core-1.0.jar
                         |
                         v
Nhóm consumer
  biên dịch legacy-client.jar
  dựa trên public API của v1
                         |
                         v
Bên vận hành
  thay thư viện runtime bằng catalog-core-2.0.jar
  mà KHÔNG biên dịch lại legacy-client.jar
~~~

Nhóm thư viện cho rằng đổi tham số `int` sang `long` là một cải tiến an toàn vì mọi `int` đều có thể chuyển sang `long` trong source Java. Kết luận ấy chỉ xét **source invocation** khi compiler có cơ hội chạy lại. Artifact consumer đã phát hành lại không dùng cơ chế overload resolution của compiler nữa; nó mang lời gọi nhị phân cố định.

Tình huống kiểu này đặc biệt quan trọng với:

- SDK/JAR được ứng dụng khách hàng nhúng vào runtime.
- Plugin framework cho phép cập nhật library mà không rebuild plugin.
- Agent, JDBC driver wrapper và adapter dùng ở nhiều service độc lập.
- Multi-module application nơi các module được phát hành ở thời điểm khác nhau.
- Container hoặc application server cấp library dùng chung.
- Thư viện nội bộ phát hành lên Maven repository với nhiều consumer chưa được đồng bộ phiên bản.

Không phải mọi dự án đều cam kết hỗ trợ binary consumers cũ. Nhưng nếu có, **thư viện mới chạy được với source mới** là tiêu chuẩn không đủ.

## 3. Ba loại tương thích cần phân biệt

| Loại | Câu hỏi | Phép kiểm |
|---|---|---|
| **Source compatibility** | Source consumer cũ có biên dịch lại với API mới không? | `javac` lại consumer source bằng library v2 |
| **Binary compatibility** | Bytecode consumer cũ có liên kết và chạy với library v2 không? | Dùng **nguyên consumer.jar cũ** cùng library v2 |
| **Behavioral compatibility** | Kết quả, lỗi, side effects và hợp đồng nghiệp vụ có còn đúng không? | Unit/integration/contract tests cùng dữ liệu |

Các kết quả có thể khác nhau:

| Source v1 với lib v2 | Binary consumer v1 với lib v2 | Diễn giải |
|---|---|---|
| PASS | PASS | Có thể tương thích ở hai mức; vẫn cần test hành vi |
| PASS | FAIL | **Trọng tâm bài:** source compile lại được nhưng artifact cũ lỗi |
| FAIL | PASS | Có thể xảy ra với một số thay đổi làm source resolution thay đổi, dù bytecode cũ vẫn có thể liên kết |
| FAIL | FAIL | Thay đổi rõ ràng phá nhiều hình thức tương thích |

**Quan trọng:** Tương thích nhị phân không cam kết tương thích hành vi. Một method giữ nguyên chữ ký nhưng đổi từ làm tròn HALF_UP sang DOWN có thể binary-compatible mà vẫn làm sai nghiệp vụ.

## 4. Chuẩn bị môi trường và cấu trúc dự án

Dùng một JDK 17 trở lên để có các công cụ `javac`, `jar`, `java` và `javap`. Cần **JDK đầy đủ**, không chỉ image JRE tối giản.

Kiểm tra phiên bản khi thực hiện trên máy học:

~~~bash
java -version
javac -version
jar --help
javap -help
~~~

Gợi ý tổ chức thư mục:

~~~text
binary-compat-lab/
  src/
    lib-v1/
      com/example/catalog/PriceService.java
    lib-v2/
      com/example/catalog/PriceService.java
    lib-v2-fixed/
      com/example/catalog/PriceService.java
    client/
      com/example/client/ClientMain.java
  out/
    lib-v1/
    lib-v2/
    lib-v2-fixed/
    client/
    client-new/
  dist/
    catalog-v1.jar
    catalog-v2.jar
    catalog-v2-fixed.jar
    client-original.jar
    client-recompiled.jar
~~~

Những thư mục `src/...` chứa source để bạn tự tạo. `out/` và `dist/` chứa artifact sinh ra trong bài. Khi làm lại bài, nên xóa riêng `out`/`dist` đã sinh rồi tạo mới để tránh dùng nhầm class cũ. Không xóa thư mục ngoài bài thực hành.

### 4.1. Lưu ý về nền tảng

Lệnh trong các bước chính dùng **Bash trên Linux/macOS**. Trên Windows PowerShell, cùng các công cụ `javac`/`jar`/`java` được dùng nhưng:

- Dấu phân cách classpath là **`;`** thay vì **`:`**.
- Tạo thư mục bằng `New-Item -ItemType Directory` hoặc công cụ tương ứng.
- Không sao chép nguyên một dòng Bash chứa `mkdir -p` sang PowerShell rồi mặc định sẽ hoạt động giống nhau.
- Các path tương đối trong ví dụ giả định command được chạy từ thư mục `binary-compat-lab`.

Ví dụ tạo thư mục đầu ra trên Bash:

~~~bash
mkdir -p out/lib-v1 out/lib-v2 out/lib-v2-fixed
mkdir -p out/client out/client-new dist
~~~

Bạn cần tạo các file source theo những đoạn code ở phần tiếp theo trước khi gọi compiler.

## 5. Tạo thư viện v1: public API ban đầu

File: `src/lib-v1/com/example/catalog/PriceService.java`

~~~java
package com.example.catalog;

public class PriceService {

    public String formatPrice(int cents) {
        return cents + " VND";
    }
}
~~~

Trong ví dụ tối giản, tên `cents` chỉ là tên tham số để mô tả một đại lượng nguyên; kết quả in `VND` được dùng để dễ đọc. Đây **không phải** mô hình nghiệp vụ tiền tệ có tính toán tỷ giá hoặc quy đổi tiền lẻ.

Điều quan trọng là **public API**:

~~~java
public String formatPrice(int cents)
~~~

Ở mức JVM, method có:

- Tên: `formatPrice`.
- Tham số: một `int`.
- Kiểu trả về: `java.lang.String`.
- Method descriptor: `(I)Ljava/lang/String;`.

Ký hiệu `I` trong descriptor nghĩa là `int`; `J` là `long`. Descriptor gồm tham số trong ngoặc và kiểu trả về sau ngoặc. JVM sử dụng thông tin nhị phân này khi liên kết lời gọi.

### 5.1. Build `catalog-v1.jar`

Chạy từ thư mục gốc bài thực hành:

~~~bash
javac --release 17 -encoding UTF-8 \
  -d out/lib-v1 \
  src/lib-v1/com/example/catalog/PriceService.java

jar --create --file dist/catalog-v1.jar \
  -C out/lib-v1 .
~~~

Giải thích:

- `--release 17` yêu cầu compiler tạo bytecode/API compatibility cho Java 17; compiler phải là JDK hỗ trợ release này.
- `-d out/lib-v1` đặt class vào đúng package directory.
- `jar --create --file` đóng class thành JAR.
- `-C out/lib-v1 .` lấy nội dung từ thư mục classes, không nhét tiền tố `out/lib-v1` vào tên package trong JAR.

Artifact v1 giờ có class:

~~~text
com/example/catalog/PriceService.class
~~~

## 6. Tạo consumer dùng thư viện v1

File: `src/client/com/example/client/ClientMain.java`

~~~java
package com.example.client;

import com.example.catalog.PriceService;

public final class ClientMain {

    public static void main(String[] args) {
        PriceService service = new PriceService();
        String output = service.formatPrice(1200);
        System.out.println(output);
    }
}
~~~

Nhìn source:

~~~java
service.formatPrice(1200)
~~~

Compiler thấy giá trị literal `1200` có kiểu `int` và giải quyết lời gọi tới `formatPrice(int)` trong `catalog-v1.jar`. Thông tin method cụ thể được ghi vào bytecode của consumer.

### 6.1. Biên dịch consumer với v1

~~~bash
javac --release 17 -encoding UTF-8 \
  -cp dist/catalog-v1.jar \
  -d out/client \
  src/client/com/example/client/ClientMain.java

jar --create --file dist/client-original.jar \
  -C out/client .
~~~

**Đây là mốc quan trọng của bài:** Sau lệnh trên, coi `dist/client-original.jar` là artifact đã được bên sử dụng phát hành. **Không sửa và không biên dịch lại JAR này** trong các bước tái hiện binary failure.

Bạn có thể lưu checksum của artifact trước khi thử:

~~~bash
sha256sum dist/client-original.jar
~~~

Trên hệ thống không có `sha256sum`, dùng công cụ checksum tương ứng, chẳng hạn PowerShell `Get-FileHash`. Mục đích là chứng minh bạn dùng nguyên một consumer artifact ở mọi lần chạy.

### 6.2. Chạy baseline bằng thư viện v1

Trên Linux/macOS:

~~~bash
java -cp "dist/catalog-v1.jar:dist/client-original.jar" \
  com.example.client.ClientMain
~~~

Kết quả dự kiến:

~~~text
1200 VND
~~~

Trên Windows PowerShell, dùng classpath `;`:

~~~powershell
java -cp "dist/catalog-v1.jar;dist/client-original.jar" com.example.client.ClientMain
~~~

Lúc này:

- Consumer bytecode được build dựa trên v1.
- Runtime có class `PriceService` từ v1.
- Method có descriptor mà consumer yêu cầu.
- Việc JVM liên kết lời gọi thành công là điều được mong đợi.

## 7. Tạo thư viện v2 với một thay đổi tưởng như vô hại

Tác giả thư viện muốn hỗ trợ những giá trị lớn hơn giới hạn `int`. Họ **thay thế** method cũ bằng method nhận `long`, không giữ lại overload cũ.

File: `src/lib-v2/com/example/catalog/PriceService.java`

~~~java
package com.example.catalog;

public class PriceService {

    public String formatPrice(long cents) {
        return cents + " VND";
    }
}
~~~

Đoạn code này **không còn**:

~~~java
public String formatPrice(int cents)
~~~

Thay vào đó chỉ còn:

~~~java
public String formatPrice(long cents)
~~~

Về mặt source Java, một lời gọi truyền `int` vẫn có thể khớp method nhận `long` do **primitive widening conversion**. Nhưng về mặt bytecode, method cũ và mới khác descriptor:

| Phiên bản | Public method | JVM method descriptor |
|---|---|---|
| v1 | `String formatPrice(int)` | `(I)Ljava/lang/String;` |
| v2 | `String formatPrice(long)` | `(J)Ljava/lang/String;` |

**V2 không bảo đảm thực thi method descriptor mà consumer cũ đã yêu cầu.**

### 7.1. Build v2 độc lập

~~~bash
javac --release 17 -encoding UTF-8 \
  -d out/lib-v2 \
  src/lib-v2/com/example/catalog/PriceService.java

jar --create --file dist/catalog-v2.jar \
  -C out/lib-v2 .
~~~

Không đưa `catalog-v1.jar` vào `catalog-v2.jar`. Bài cần một JAR v2 chứa **chỉ phiên bản mới** của `PriceService`.

## 8. Tái hiện lỗi: thay library mà giữ nguyên consumer binary

Chạy **chính consumer JAR gốc** với library v2:

~~~bash
java -cp "dist/catalog-v2.jar:dist/client-original.jar" \
  com.example.client.ClientMain
~~~

Trên Windows:

~~~powershell
java -cp "dist/catalog-v2.jar;dist/client-original.jar" com.example.client.ClientMain
~~~

Kết quả dự kiến là lỗi tương tự:

~~~text
Exception in thread "main" java.lang.NoSuchMethodError:
  'java.lang.String com.example.catalog.PriceService.formatPrice(int)'
    at com.example.client.ClientMain.main(ClientMain.java:...)
~~~

Số dòng, cách hiển thị descriptor và chi tiết stack trace có thể khác theo JDK/compiler. **Ý nghĩa cốt lõi** không đổi: consumer binary đang yêu cầu method `formatPrice(int)` mà class v2 không cung cấp.

### 8.1. Điều gì đã xảy ra?

~~~text
Build time                         Runtime

catalog-v1.jar                     catalog-v2.jar
  formatPrice(int)                   formatPrice(long)
        |                                   |
        v                                   |
javac compiles client                     |
        |                                   |
        v                                   |
client-original.jar                         |
  invokevirtual                            |
  PriceService.formatPrice:(I)Ljava/lang/String;
        |                                   |
        +---------- runtime link ----------+
                                            |
                                  Cannot find method
                                  descriptor (I)...
                                            |
                                       NoSuchMethodError
~~~

JVM **không chạy lại phép chọn overload của javac** khi link bytecode cũ. Một method có tên giống nhưng tham số `long` không phải replacement nhị phân cho method có tham số `int`.

### 8.2. Vì sao lỗi có thể không xuất hiện ngay lúc startup?

JVM có thể trì hoãn việc resolve một số symbolic references đến khi code path thực thi. Nếu `formatPrice(int)` chỉ được gọi khi tạo hóa đơn, ứng dụng có thể khởi động và qua healthcheck nhưng fail khi xử lý một request cụ thể.

Bởi vậy, **smoke test khởi động thành công** không bảo đảm mọi consumer invocation đều tương thích. Cần các contract/integration tests thực sự gọi public API đã phát hành.

## 9. Bằng chứng: dùng javap đọc method descriptors

`javap` là công cụ trong JDK giúp xem chữ ký nhị phân của class. Không cần đoán từ source khi đã có artifact.

### 9.1. Xem API của thư viện v1

~~~bash
javap -s -classpath dist/catalog-v1.jar \
  com.example.catalog.PriceService
~~~

Phần cần quan sát trong output dự kiến:

~~~text
public java.lang.String formatPrice(int);
  descriptor: (I)Ljava/lang/String;
~~~

### 9.2. Xem API của thư viện v2

~~~bash
javap -s -classpath dist/catalog-v2.jar \
  com.example.catalog.PriceService
~~~

Phần quan trọng:

~~~text
public java.lang.String formatPrice(long);
  descriptor: (J)Ljava/lang/String;
~~~

Các dòng này minh họa **những thành phần cần tìm**, không phải output đầy đủ đã được ghi lại từ tool.

### 9.3. Xem lời gọi trong consumer artifact gốc

~~~bash
javap -c -p -classpath dist/client-original.jar \
  com.example.client.ClientMain
~~~

Một comment của disassembler ở instruction `invokevirtual` có thể có dạng:

~~~text
Method com/example/catalog/PriceService.formatPrice:(I)Ljava/lang/String;
~~~

Bằng chứng gồm ba phần:

1. Consumer cũ yêu cầu descriptor `(I)Ljava/lang/String;`.
2. Library v2 chỉ cung cấp descriptor `(J)Ljava/lang/String;`.
3. Khi gọi code path đó, runtime không tìm được method cũ và ném `NoSuchMethodError`.

Đó là **root cause nhị phân**, không phải lỗi ép kiểu khi compile source.

### 9.4. Vì sao return type cũng quan trọng?

Trong JVM method descriptor, **kiểu trả về là một phần descriptor**. Thay `String` thành `Object` mà không có phương thức/cầu nối tương thích cũng có thể làm hỏng lời gọi cũ, dù trong Java source một phép gán có thể tiếp tục compile ở vài tình huống.

Ngược lại, compiler Java có thể tạo bridge methods trong một số trường hợp covariant return/generics để duy trì polymorphism. Không nên dựa vào việc compiler luôn tự tạo bridge cho một thay đổi API bất kỳ. Với thay đổi `int` sang `long` trong bài này, compiler **không tự bảo toàn** `formatPrice(int)`.

## 10. Thử biên dịch lại consumer source với v2

Hãy chạy cùng file source `ClientMain.java` nhưng dùng library v2 trên compile classpath:

~~~bash
javac --release 17 -encoding UTF-8 \
  -cp dist/catalog-v2.jar \
  -d out/client-new \
  src/client/com/example/client/ClientMain.java

jar --create --file dist/client-recompiled.jar \
  -C out/client-new .
~~~

Lệnh biên dịch dự kiến **thành công** vì lời gọi `formatPrice(1200)` dùng một `int` có thể chuyển kiểu lên `long` cho method v2.

Chạy artifact **mới biên dịch**:

~~~bash
java -cp "dist/catalog-v2.jar:dist/client-recompiled.jar" \
  com.example.client.ClientMain
~~~

Kết quả dự kiến:

~~~text
1200 VND
~~~

Bây giờ có hai trạng thái rõ ràng:

| Consumer artifact | Library runtime | Kết quả dự kiến |
|---|---|---|
| `client-original.jar` build với v1 | `catalog-v1.jar` | PASS |
| `client-original.jar` build với v1 | `catalog-v2.jar` | **FAIL: NoSuchMethodError** |
| `client-recompiled.jar` build với v2 | `catalog-v2.jar` | PASS |

Đây là bài học trung tâm: **source compatibility không đồng nghĩa binary compatibility**.

### 10.1. Không dùng “rebuild hết” để chứng minh thư viện vẫn tương thích

Nếu sản phẩm cho phép consumer bắt buộc rebuild khi nâng major version, đó có thể là một chính sách hợp lệ. Nhưng quyết định ấy cần được công bố trong hợp đồng phát hành.

Nếu mục tiêu là **không phá artifact consumer cũ**, việc chỉ biên dịch lại consumer thành công **không giải quyết yêu cầu**. Bài test cuối phải dùng `client-original.jar` ban đầu.

## 11. Sửa v2 bằng compatibility bridge

Giải pháp của bài là giữ API cũ và thêm API mới. Method cũ có thể chuyển tiếp (delegate) sang method nhận `long`.

File: `src/lib-v2-fixed/com/example/catalog/PriceService.java`

~~~java
package com.example.catalog;

public class PriceService {

    /**
     * Legacy entry point used by consumers compiled with v1.
     */
    @Deprecated(since = "2.0", forRemoval = false)
    public String formatPrice(int cents) {
        return formatPrice((long) cents);
    }

    /**
     * New API accepting a wider numeric range.
     */
    public String formatPrice(long cents) {
        return cents + " VND";
    }
}
~~~

Cơ chế này thường được gọi là **compatibility overload** hoặc **manual bridge**. Nó khác bridge method do compiler tự sinh cho một số tình huống generics/covariant returns; ở đây tác giả thư viện **chủ động** giữ method cũ trong public ABI.

### 11.1. Vì sao cần ép kiểu `(long)` trong overload?

~~~java
public String formatPrice(int cents) {
    return formatPrice((long) cents);
}
~~~

Dùng ép kiểu giúp thấy rõ lời gọi chuyển sang overload mới nhận `long`. Nó tránh sự mơ hồ khi đọc code, và bảo đảm không vô tình gọi đệ quy lại `formatPrice(int)`.

### 11.2. Khi nào không nên chỉ delegate?

Với ví dụ này, hành vi v1/v2 giống nhau với input `int`. Nhưng trong một API thực tế, có thể tồn tại:

- Giá trị biên `int` mà v2 xử lý khác.
- Thay đổi rounding, timezone hoặc encoding.
- Thay đổi checked/unchecked exceptions.
- Thay đổi semantics của tham số.
- Side effect, retry, transaction hoặc ordering khác.

Khi đó giữ descriptor cũ **chưa đủ**. Bridge phải bảo toàn hợp đồng hành vi cho những consumer vẫn sử dụng API cũ, hoặc thay đổi phải được công bố rõ.

## 12. Build thư viện đã sửa

~~~bash
javac --release 17 -encoding UTF-8 \
  -d out/lib-v2-fixed \
  src/lib-v2-fixed/com/example/catalog/PriceService.java

jar --create --file dist/catalog-v2-fixed.jar \
  -C out/lib-v2-fixed .
~~~

Dùng `javap` quan sát:

~~~bash
javap -s -classpath dist/catalog-v2-fixed.jar \
  com.example.catalog.PriceService
~~~

Kết quả kỳ vọng chứa cả hai method:

~~~text
public java.lang.String formatPrice(int);
  descriptor: (I)Ljava/lang/String;

public java.lang.String formatPrice(long);
  descriptor: (J)Ljava/lang/String;
~~~

Annotation `@Deprecated` giúp nhắc người viết source mới về API cũ; nó **không xóa method khỏi bytecode** và không làm consumer cũ bị lỗi chỉ vì method được đánh dấu deprecated. Với JDK thấp hơn Java 9, thuộc tính `since`/`forRemoval` của `@Deprecated` không sẵn có, nên mã nguồn cần điều chỉnh theo baseline thực tế.

## 13. Kiểm lại bằng chính consumer artifact cũ

Đây là phép kiểm quan trọng nhất của bài. **Không biên dịch lại `client-original.jar`.**

Chạy:

~~~bash
java -cp "dist/catalog-v2-fixed.jar:dist/client-original.jar" \
  com.example.client.ClientMain
~~~

Kết quả dự kiến:

~~~text
1200 VND
~~~

Ma trận sau khi sửa:

| Consumer | Library | Kỳ vọng |
|---|---|---|
| Original v1-compiled JAR | v1 | PASS |
| Original v1-compiled JAR | v2 broken | FAIL |
| Original v1-compiled JAR | v2 fixed | **PASS** |
| Recompiled-v2 JAR | v2 fixed | PASS nếu contract phù hợp |

Nếu bốn trạng thái đúng như dự kiến, bài thực hành đã chứng minh:

- Việc đổi `int` thành `long` **theo hướng xóa method cũ** phá binary compatibility.
- Recompile consumer giúp source thích nghi, nhưng không làm artifact cũ hoạt động với v2 broken.
- Giữ lại đúng method descriptor cũ cho phép consumer artifact cũ liên kết thành công.
- Kiểm kết quả nghiệp vụ vẫn cần thực hiện sau khi method đã link thành công.

### 13.1. Điều gì cần bất biến?

`client-original.jar` phải giữ nguyên **nội dung/checksum** từ lúc được tạo ở bước 6. Nếu vô tình rebuild hoặc ghi đè file này, bài test cuối sẽ không còn chứng minh backward binary compatibility.

Trong team thật, artifact consumer cũ nên được lấy từ bản phát hành đã công bố hoặc fixture JAR được version-control/đóng gói riêng, không được build lại bằng dependency mới trước mỗi lần kiểm.

## 14. Vì sao NoSuchMethodError là LinkageError?

`NoSuchMethodError` là một dạng `IncompatibleClassChangeError` trong nhánh `LinkageError`. Nó thường xảy ra khi class đang thực thi được biên dịch với một phiên bản API nhưng runtime lại cung cấp một class khác không có method nhị phân được yêu cầu.

Ví dụ logic:

~~~text
Compile classpath:
  catalog-core 1.0.0

Consumer bytecode:
  invokes PriceService.formatPrice:(I)Ljava/lang/String;

Runtime classpath:
  catalog-core 2.0.0

Runtime symbol resolution:
  PriceService loaded
  method name = formatPrice
  descriptor = (I)Ljava/lang/String;
  matching method absent
  => NoSuchMethodError
~~~

Không phải lỗi của numeric conversion hoặc thiếu object Java trên heap. Ở thời điểm này, JVM đã tìm được class `PriceService` nhưng không tìm được **method cụ thể** trong class/hierarchy theo quy tắc liên kết.

### 14.1. Khác gì với NoClassDefFoundError?

| Lỗi | Ý nghĩa thường gặp |
|---|---|
| `NoSuchMethodError` | Class đã được resolve nhưng thiếu method cần gọi với descriptor tương ứng |
| `NoSuchFieldError` | Bytecode cần field đã thay đổi/bị xóa |
| `NoClassDefFoundError` | JVM không có class definition cần thiết khi đang dùng class; cũng có thể do lỗi khởi tạo class trước đó |
| `ClassNotFoundException` | Một API tải class theo tên (ví dụ `Class.forName`) không tìm được class |
| `IllegalAccessError` | Thay đổi access hoặc linkage khiến code không được quyền truy cập member/class |
| `IncompatibleClassChangeError` | Hình thức class/member thay đổi không tương thích, ví dụ instance/static mismatch |
| `AbstractMethodError` | Lời gọi yêu cầu implementation của method nhưng runtime không có implementation hợp lệ |
| `UnsupportedClassVersionError` | Runtime không hiểu class-file version quá mới |

Khi debug, phải đọc **tên class + tên method + descriptor trong thông báo**, không sửa ngẫu nhiên mọi dependency.

## 15. Điều tra khi runtime có nhiều JAR cùng chứa một class

Trong ứng dụng thật, lỗi có thể xảy ra dù file library mới **có method đúng**, bởi JVM lại tải `PriceService` từ **một JAR khác** do classpath/module loading.

Ví dụ:

~~~text
lib/catalog-v2-fixed.jar   (has formatPrice(int))
lib/catalog-v2-broken.jar  (has only formatPrice(long))
app/legacy-client.jar
~~~

Nếu cả hai library versions cùng nằm trên classpath, class loader có thể chọn phiên bản không mong muốn. Không nên dựa vào việc đảo thứ tự JAR như chiến lược release dài hạn.

### 15.1. Kiểm các class trùng và nơi tải class

Đầu tiên, liệt kê nội dung JAR:

~~~bash
jar --list --file dist/catalog-v1.jar
jar --list --file dist/catalog-v2.jar
jar --list --file dist/catalog-v2-fixed.jar
~~~

Trên JDK 9+ có thể dùng class loading log:

~~~bash
java -Xlog:class+load=info \
  -cp "dist/catalog-v2.jar:dist/client-original.jar" \
  com.example.client.ClientMain
~~~

Dùng `-Xlog:class+load=info` cho một phiên chẩn đoán có chủ đích vì log có thể nhiều. Nội dung có thể ghi nguồn class đã tải; tìm `com.example.catalog.PriceService` để xác định JAR nào thực sự cung cấp class.

### 15.2. In CodeSource để hỗ trợ chẩn đoán

Nếu bạn đang chỉnh được source của một chương trình diagnostic:

~~~java
import com.example.catalog.PriceService;

public class SourceProbe {
    public static void main(String[] args) {
        var location =
            PriceService.class.getProtectionDomain()
                .getCodeSource();

        System.out.println(
            location == null
                ? "No CodeSource available"
                : location.getLocation());
    }
}
~~~

Đoạn này là công cụ hỗ trợ, không phải chứng cứ đủ cho mọi custom class loader; `CodeSource` có thể `null`. Với ứng dụng dùng fat JAR, module path hoặc container class loader, nguồn class có thể có cách biểu diễn khác.

## 16. Sai lầm phổ biến: classpath chứa cả v1 và v2

Một cách chạy không sạch:

~~~bash
java -cp "dist/catalog-v1.jar:dist/catalog-v2.jar:dist/client-original.jar" \
  com.example.client.ClientMain
~~~

Kết quả có thể **đánh lừa**: nếu JVM tải class từ v1 trước, client pass dù v2 broken vẫn tồn tại. Đảo thứ tự có thể khiến fail. Nhưng ngay cả khi biết classpath order, đóng gói nhiều phiên bản của cùng class vào một loader không phải cách giải quyết compatibility đáng tin cậy.

Trong bài này, mỗi lần chạy phải chỉ có **một** trong các JAR library v1, v2 hoặc v2-fixed, kèm đúng một client JAR. Đây là cách kiểm soát biến để thấy rõ nguyên nhân.

### 16.1. Class loader khác nhau có thể làm tình huống phức tạp hơn

Trong application server hoặc plugin system, các class loader có thể tạo namespace riêng cho class cùng tên. Nhưng việc “trùng class ở hai loader” có thể gây `ClassCastException`, service provider mismatch hoặc type identity conflict. Bài thực hành dùng classpath đơn giản để cô lập binary method resolution.

Không tự thêm nhiều library versions vào runtime với kỳ vọng loader luôn “chọn bản phù hợp cho từng consumer”. Muốn side-by-side isolation phải có thiết kế class loader/module boundary rõ, không phải chiến lược mặc định.

## 17. Nhận diện cùng lỗi trong Gradle

Một dự án Gradle có thể compile consumer với catalog-core v1 nhưng runtime resolve v2 do dependency khác hoặc configuration khác. Điều này có thể do transitive dependency, version constraints, platform/BOM hoặc việc build/packaging dùng tập dependency không nhất quán.

Ví dụ điều tra Gradle:

~~~bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight \
  --configuration runtimeClasspath \
  --dependency catalog-core
~~~

Lệnh chỉ minh họa, **không phải test đã chạy**. Trong multi-project build, cần chọn đúng project và configuration, ví dụ `:consumer:dependencies`. Kiểm cả:

- Library version trên compile classpath.
- Library version trên runtime classpath.
- Các dependency transitively yêu cầu version khác.
- Gradle dependency constraints và resolution strategy.
- JAR thực sự được đóng vào distribution/container.
- Các artifact được lấy từ repository nội bộ hay cache.
- Consumer JAR cũ có bị rebuild hay không.

### 17.1. Compile thành công không phản ánh runtime graph

Gradle có thể giải quyết compile/runtime configurations khác nhau. Nếu runtime chỉ có thư viện v2 broken, consumer JAR cũ vẫn có thể ném `NoSuchMethodError` ngay cả khi build mới của thư viện xanh.

Để phát hiện, nên có **consumer compatibility test** dùng artifact đã phát hành trước đó và chạy với candidate library, thay vì chỉ chạy unit tests nằm trong module library.

### 17.2. Không ép một version cũ làm giải pháp tạm thời vô hạn

Pin về v1 có thể giúp khôi phục service trong incident, nhưng nếu cần sửa security hoặc tính năng trên v2, cần giải pháp nâng cấp bền vững. Nhóm phải quyết định:

- Xuất bản v2-fixed có method bridge.
- Nâng/rebuild tất cả consumers có kiểm soát.
- Phát hành major breaking version theo hợp đồng với migration guide.
- Sử dụng adapter riêng với contract rõ ràng khi không sửa được library.

## 18. Nhận diện cùng lỗi trong Maven

Ở Maven, có thể dùng dependency tree để xác định bản thực sự được chọn:

~~~bash
./mvnw dependency:tree
~~~

Đối với một artifact mục tiêu, có thể lọc theo group/artifact dựa trên plugin version được sử dụng. Đọc cả parent POM, dependency management, BOM và transitive resolution.

Một dependency declaration minh họa:

~~~xml
<dependency>
  <groupId>com.example</groupId>
  <artifactId>catalog-core</artifactId>
  <version>2.0.0</version>
</dependency>
~~~

Nếu một consumer JAR đã compile với version 1.0.0 được thả vào ứng dụng runtime dùng 2.0.0, dependency declaration trên **không tự làm consumer binary được biên dịch lại**. Maven chỉ giải quyết classpath/artifacts; JVM vẫn liên kết method descriptors từ bytecode thực có.

Một lệnh `mvn clean verify` pass trên source mới không thay thế phép thử original consumer artifact. Với public library, cân nhắc build một compatibility fixture project không bị cập nhật binary tự động.

## 19. API thay đổi nào còn có thể phá artifact cũ?

Bài này dùng `int` → `long`, nhưng binary break có nhiều dạng.

| Thay đổi thư viện | Rủi ro với consumer đã compile |
|---|---|
| Xóa/đổi tên public method | `NoSuchMethodError` |
| Đổi kiểu tham số | Method descriptor khác; có thể `NoSuchMethodError` |
| Đổi kiểu trả về | Descriptor khác; có thể lỗi linkage |
| Đổi instance method thành static hoặc ngược lại | `IncompatibleClassChangeError` |
| Xóa public field hoặc đổi kiểu field | `NoSuchFieldError` |
| Thu hẹp public thành private/package-private | `IllegalAccessError` hoặc lỗi linkage |
| Xóa một class public được consumer tham chiếu | `NoClassDefFoundError` hoặc loading failure |
| Thay đổi abstract/concrete hierarchy | Có thể `AbstractMethodError` khi invocation |
| Đổi package `javax.*` sang `jakarta.*` | Type identity khác; consumer cũ cần adapter hoặc rebuild |
| Thêm overload mới | Thường không phá lời gọi bytecode cũ nếu method cũ còn, nhưng có thể khiến source compile lại ambiguous |
| Đổi logic giữ nguyên signature | Có thể phá **behavioral compatibility** dù binary link vẫn tốt |

Đây là các **hướng nguy cơ**, không phải khẳng định cứ làm thay đổi đó thì JVM luôn ném đúng một exception bất kể hierarchy/call site. Kết quả phụ thuộc cách method được gọi, supertype, class loader và metadata thực tế. Phân tích theo JLS Chương 13 và JVMS resolution khi cần kết luận chính xác.

## 20. Thêm overload thường giữ binary compatibility nhưng có thể làm source khác

Ví dụ thư viện v1:

~~~java
public String describe(Object input) {
    return "object";
}
~~~

Thư viện v2 giữ method cũ và thêm:

~~~java
public String describe(String input) {
    return "string";
}
~~~

Một consumer **đã biên dịch** với v1 gọi `describe(null)` vẫn có reference tới `describe(Object)`. Sau khi rebuild với v2, compiler có thể chọn `describe(String)` vì nó cụ thể hơn, dẫn đến thay đổi hành vi.

Trường hợp khác, thêm hai overload không quan hệ có thể làm source call `describe(null)` trở nên **ambiguous**. Như vậy:

- Thêm overload thường an toàn hơn về binary nếu vẫn giữ method cũ.
- Nhưng không phải mọi overload addition đều bảo đảm source/behavior compatibility.
- Cần test cả original binary và source recompilation nếu muốn công bố cả hai loại tương thích.

## 21. SemVer: đổi version không tự bảo đảm API compatibility

Nhiều thư viện dùng Semantic Versioning với quy ước:

- Patch: sửa lỗi, không cố ý đổi API không tương thích.
- Minor: thêm tính năng tương thích.
- Major: cho phép breaking changes được công bố.

Trong bài, xóa `formatPrice(int)` có tính chất **binary breaking**, dù source phổ biến vẫn compile lại được. Một thay đổi như vậy thường cần **major release** nếu thư viện áp dụng SemVer và cam kết API/ABI tương ứng.

Tuy nhiên, chỉ đặt version 2.0.0 **không làm artifact consumer cũ tự hoạt động**. Versioning là cách **truyền đạt hợp đồng**, còn binary compatibility là thuộc tính kỹ thuật phải kiểm.

### 21.1. Giữ bridge bao lâu?

Tùy chính sách thư viện:

- Nếu library cam kết tương thích nhị phân lâu dài, giữ method cũ đến khi có kế hoạch major breaking cụ thể.
- Nếu đã thông báo major migration yêu cầu rebuild consumer, có thể không cần bridge — nhưng phải có consumer upgrade plan.
- Nếu method cũ có rủi ro bảo mật, cần cân nhắc deprecate/disable theo chính sách thay vì giữ vô thời hạn.
- Nếu method bridge giữ được semantics mà chi phí thấp, nó thường là lựa chọn tốt để giảm rủi ro rollout.

Không tự đặt `forRemoval=true` rồi xóa ở release tiếp theo mà thiếu thời gian chuyển đổi và kiểm consumer thực tế.

## 22. Đặt compatibility test vào pipeline phát hành thư viện

Một pipeline đủ mạnh cho thư viện có consumers cũ thường có hai luồng độc lập:

~~~text
Candidate catalog-core v2
        |
        +--> Library's own tests
        |       compile new sources
        |       test new API
        |
        +--> Binary consumer compatibility tests
                take client-original.jar from v1 fixture
                load candidate catalog-core v2
                invoke published API calls
                inspect linkage and behavior
                |
                +--> PASS: candidate keeps old contract
                +--> FAIL: breaking change found
~~~

Test nhánh thứ hai không được lặng lẽ rebuild consumer cũ với v2. Nếu phải tạo test fixture binary, hãy build nó **một lần theo API cũ**, lưu artifact/checksum trong một nguồn có kiểm soát và dùng lại.

### 22.1. Điều gì nên thành release gate?

| Gate | Kiểm gì | Bằng chứng |
|---|---|---|
| Build candidate | Thư viện v2 compile và package đúng | JAR + build report |
| API surface diff | Public classes/method descriptors thay đổi ra sao | Tool report |
| Source compatibility | Consumer source cũ compile lại được không | Compiler report |
| Binary compatibility | Consumer bytecode cũ chạy với candidate không | Runtime/JUnit test |
| Behavior compatibility | Output/exceptions/side effects giữ đúng không | Contract tests |
| Dependency resolution | Không có nhiều version class trùng ngoài ý muốn | Resolved graph, artifact scan |
| JDK runtime matrix | Chạy trên min/supported JDK | Runtime logs và test report |
| Release policy | Breaking changes có được công bố/phê duyệt | Changelog/migration guide |

Một dự án có thể chọn các gate khác nhau theo mức cam kết. Quan trọng là không dùng một gate để giả làm bằng chứng của gate khác.

## 23. Công cụ API/ABI diff

Khi có hai library JAR, ngoài `javap` có thể dùng các công cụ kiểm tra API/binary compatibility như:

- **japicmp**: so class/interface/method descriptors và các loại compatibility changes giữa hai JAR.
- **Revapi**: phân tích thay đổi API theo cấu hình và policy.
- **bnd baseline**: đánh giá API/package versioning ở bối cảnh OSGi khi phù hợp.
- **jdeps**: phân tích quan hệ dependency/module và reference; không phải công cụ xác nhận đầy đủ method-level binary compatibility của mọi consumer.

Các công cụ này cần được cấu hình theo phiên bản plugin/tool hỗ trợ JDK và theo phạm vi API công khai. Chúng không tự phát hiện mọi breaking behavioral change.

Ví dụ yêu cầu mức policy:

~~~text
Compare:
  catalog-v1.jar
  catalog-v2.jar

Reject release if:
  public method formatPrice:(I)Ljava/lang/String;
  disappears without an approved breaking change.

Allow release if:
  v2 keeps descriptor (I)...
  and contract test using original consumer JAR passes.
~~~

Không coi ví dụ này là file cấu hình hợp lệ cho một plugin cụ thể. Mỗi tool có schema/version riêng.

## 24. Một bài kiểm thử tự động cần chạy artifact nào?

Để tránh false pass, test harness nên tham chiếu trực tiếp:

~~~text
Original binary fixture:
  dist/client-original.jar
    compiled with catalog-v1.jar

Candidate runtime library:
  dist/catalog-v2-fixed.jar
    built from current candidate

Runtime:
  java -cp catalog-v2-fixed.jar:client-original.jar
  com.example.client.ClientMain
~~~

Nếu dùng Gradle, một custom `JavaExec` task có thể đưa hai artifact vào classpath, nhưng phải tránh:

- Đưa `catalog-v1.jar` vào runtime classpath cùng candidate.
- Tự động gọi compile task của client source bằng candidate trước khi chạy.
- Dùng project dependency làm Gradle chọn class file thay vì JAR đã phát hành.
- Lấy consumer fixture từ cache không đúng version.
- Chạy test trên JDK khác runtime được công bố.
- Chỉ kiểm exit code trong khi output sai nghiệp vụ.

Nếu app có nhiều consumer modules, có thể xây một tập **consumer fixtures** theo phiên bản đáng hỗ trợ để test không bị giới hạn ở một sample client.

## 25. Khác biệt giữa Java bytecode version và API binary compatibility

Một consumer JAR được biên dịch cho Java 17 thường có thể chạy trên các JDK mới hỗ trợ class-file version ấy, nhưng điều đó **không cam kết** thư viện runtime sẽ giữ API nhị phân.

Hai vấn đề khác nhau:

- `UnsupportedClassVersionError`: JVM quá cũ không đọc được bytecode được tạo cho version mới.
- `NoSuchMethodError`: JVM đọc được class nhưng lúc resolve method reference không tìm thấy method nhị phân phù hợp.

Vì vậy, một SDK có thể mang bytecode target Java 17 vẫn phá consumer Java 17 khi thay một public method. Ngược lại, một library giữ đầy đủ method API nhưng build bằng bytecode Java 21 sẽ không chạy trên Java 17 dù method descriptors vẫn tồn tại.

### 25.1. `--release` không kiểm ABI của dependency đã đóng gói

Khi dùng:

~~~bash
javac --release 17 ...
~~~

compiler kiểm Java language/API baseline cho source được biên dịch. Nó không kiểm “library v2 có giữ toàn bộ method descriptors của library v1 cho mọi consumer đã phát hành hay không”. Muốn biết điều đó cần API diff và binary consumer tests.

## 26. Thực hành mở rộng A: thay kiểu trả về

Tạo một biến thể của thư viện v2 (ở một thư mục thực hành riêng, **không ghi đè v2 đã dùng**) với method:

~~~java
public Object formatPrice(int cents) {
    return cents + " VND";
}
~~~

Source consumer:

~~~java
String output = service.formatPrice(1200);
~~~

không còn compile nếu method thực sự chỉ trả `Object`. Consumer binary cũ vẫn yêu cầu `(I)Ljava/lang/String;`, còn library mới cung cấp `(I)Ljava/lang/Object;`, nên có nguy cơ linkage failure.

**Câu hỏi:** Vì sao return type xuất hiện trong JVM descriptor dù Java language không cho overload methods chỉ khác return type?

Gợi ý: xem `javap -s` và quy tắc method descriptors trong JVMS. Không lẫn quy tắc overload resolution ở source với biểu diễn method trong class file.

## 27. Thực hành mở rộng B: instance method thành static

Thử biến đổi:

~~~java
public static String formatPrice(int cents) {
    return cents + " VND";
}
~~~

trong một thư viện khác có cùng class name. Consumer binary v1 đã biên dịch lời gọi theo kiểu **instance invocation**, còn method mới là **static**. Đây là loại thay đổi class/member không tương thích, có thể ném `IncompatibleClassChangeError` trong runtime phù hợp.

**Câu hỏi:** Vì sao chỉ giữ nguyên tên, tham số và return type vẫn chưa đủ?

Gợi ý: bytecode invocation opcode (`invokevirtual` so với `invokestatic`) và hình thức method là một phần của hợp đồng liên kết.

Không cần xây ứng dụng web hay thêm dependency để thử; giữ bài nhỏ và thay đúng một biến.

## 28. Thực hành mở rộng C: xóa class public

Thay `com.example.catalog.PriceService` bằng class mới `com.example.catalog.PricingService`, không giữ class cũ. Consumer artifact v1 vẫn chứa reference tới `PriceService`. Tùy code path/class loading, runtime có thể gặp `NoClassDefFoundError`.

Một lớp adapter cũ có thể giúp:

~~~java
package com.example.catalog;

@Deprecated
public final class PriceService {
    private final PricingService delegate =
            new PricingService();

    public String formatPrice(int cents) {
        return delegate.formatPrice((long) cents);
    }
}
~~~

Ví dụ giả định `PricingService` tồn tại, có method tương ứng và contract hành vi được giữ. Mục đích là giữ tên class + method cũ cho consumer, không chỉ đổi source import.

## 29. Thực hành mở rộng D: lỗi ở interface và plugin

Giả sử một interface public trong thư viện v1:

~~~java
package com.example.spi;

public interface PricePlugin {
    String formatPrice(int cents);
}
~~~

Một plugin được biên dịch với v1:

~~~java
public final class LegacyPricePlugin
        implements PricePlugin {

    @Override
    public String formatPrice(int cents) {
        return cents + " VND";
    }
}
~~~

Nếu interface v2 thay `formatPrice(int)` bằng `formatPrice(long)`, plugin binary cũ không tự xuất hiện implementation cho method mới. Khi caller gọi method mới qua interface, có thể gặp lỗi linkage như `AbstractMethodError` tùy lời gọi và hierarchy thực tế.

Giải pháp cần cân nhắc:

- Giữ method interface cũ trong giai đoạn chuyển đổi.
- Dùng default methods/adapter **sau khi phân tích nghĩa và binary contract**.
- Phát hành plugin SPI major version và hướng dẫn rebuild.
- Test những plugin JAR cũ được phân phối độc lập.

Tình huống interface thường phức tạp hơn class có method cụ thể vì còn dispatch, inheritance và default methods. Không tự suy một bridge trên interface luôn bảo toàn mọi consumer.

## 30. Tại sao chỉ có unit tests của library thường không phát hiện lỗi?

Unit test của catalog v2 có thể viết:

~~~java
@Test
void formatsLargeValues() {
    PriceService service = new PriceService();
    assertEquals("1200 VND", service.formatPrice(1200L));
}
~~~

Nếu test này được biên dịch cùng v2, nó chỉ dùng method `formatPrice(long)`. Nó không kiểm bản v1 từng cung cấp `formatPrice(int)`.

Ngay cả khi test gọi `service.formatPrice(1200)` (literal `int`), compiler khi build trên v2 sẽ chọn method `long` và test vẫn pass. **Điểm thiếu là artifact đã biên dịch với v1.**

Vì vậy, library unit tests và compatibility tests là **hai tầng bổ sung**, không thay thế nhau.

## 31. Bộ điều kiện hoàn thành cho học viên

Sau khi thực hiện thực tế trên môi trường học, hãy thu thập:

| Kiểm tra | Kết quả mong đợi |
|---|---|
| Build `catalog-v1.jar` | JAR tạo thành công |
| Build `client-original.jar` với v1 | JAR tạo thành công |
| Chạy original client + v1 | In `1200 VND` |
| Build `catalog-v2.jar` | JAR tạo thành công |
| Chạy original client + v2 | **`NoSuchMethodError`** |
| `javap` original client | Reference tới `formatPrice:(I)Ljava/lang/String;` |
| `javap` v2 | Chỉ có `formatPrice(long)`, descriptor `(J)...` |
| Compile lại client source với v2 | Thành công |
| Chạy recompiled client + v2 | In `1200 VND` |
| Build v2-fixed | Có cả method `int` và `long` |
| Chạy **original** client + v2-fixed | In `1200 VND` |
| Checksum của original client | Không đổi giữa baseline và lần chạy cuối |

Những kết quả này là **kỳ vọng của bài**, không phải báo cáo kiểm thử đã diễn ra. Nếu kết quả khác, trước tiên xác minh classpath đang chứa đúng một phiên bản thư viện và consumer JAR ban đầu chưa bị rebuild.

### 31.1. Câu hỏi kiểm tra hiểu bài

1. Vì sao `formatPrice(1200)` biên dịch lại với `long` được nhưng bytecode cũ không liên kết?
2. JVM descriptor của `formatPrice(int)` là gì? Của `formatPrice(long)` là gì?
3. Vì sao unit test mới của library v2 có thể PASS dù consumer v1 binary FAIL?
4. Trong tình huống nào có thể chấp nhận v2 phá binary compatibility?
5. Khác biệt giữa `NoSuchMethodError` và `UnsupportedClassVersionError` là gì?
6. Nếu trong runtime có hai JAR cùng chứa `PriceService`, vì sao một lần chạy PASS chưa đáng tin?
7. Thêm overload/bridge đã đủ để bảo đảm behavioral compatibility chưa?
8. Muốn tự động ngăn lỗi này, nên giữ artifact nào làm fixture trong CI?

## 32. Mẫu báo cáo điều tra sự cố

~~~yaml
incident:
  title: "Legacy consumer fails after catalog-core upgrade"
  type: "BINARY_COMPATIBILITY"
  consumer:
    artifact: "client-original.jar"
    compiledAgainst: "catalog-core 1.0"
    rebuiltDuringTest: false
  runtime:
    candidateLibrary: "catalog-core 2.0"
    jdk: "record exact java -version"
  failure:
    error: "java.lang.NoSuchMethodError"
    symbol: "PriceService.formatPrice:(I)Ljava/lang/String;"
  evidence:
    v1Descriptor: "(I)Ljava/lang/String;"
    v2Descriptor: "(J)Ljava/lang/String;"
    originalConsumerChecksum: "record sha256"
    javapReport: "attach disassembly excerpt"
  remediation:
    approach: "restore legacy overload"
    candidate: "catalog-core 2.0.1"
  validation:
    baselineRun: "NOT_YET_RUN"
    incompatibleRun: "NOT_YET_RUN"
    fixedRun: "NOT_YET_RUN"
  owner: "library-maintainers"
~~~

Mẫu minh họa này cần được điền bằng **kết quả chạy thật** nếu dùng trong dự án. Không đổi `NOT_YET_RUN` thành PASS trước khi có bằng chứng. Trong sự cố thật, nên ghi thêm runtime classpath, dependency graph, class loader nguồn class, JDK vendor/build, container image và tác động tới consumer.

## 33. Quy trình phát hành thư viện có consumer cũ

### Bước 1 — Kiểm kê API công khai

Liệt kê public classes, constructors, methods, fields, interfaces, generic signatures và module exports. Xác định phần nào là hợp đồng ổn định, phần nào là internal/experimental.

### Bước 2 — Lưu phiên bản baseline

Giữ bản phát hành cũ và artifact consumers đã compile với nó. Lưu checksum và bộ test contract, không rebuild fixture theo candidate.

### Bước 3 — Build candidate

Tạo JAR mới trên compiler/JDK phù hợp với minimum runtime được công bố. Không chỉ dựa vào việc IDE build thành công.

### Bước 4 — So API/ABI

Dùng `javap` hoặc công cụ như japicmp/Revapi để phát hiện public method descriptors bị xóa/thay đổi. Kiểm policy breaking change rõ ràng.

### Bước 5 — Chạy binary consumer tests

Đưa candidate library và original consumer JAR vào runtime sạch, không có phiên bản library cũ trùng class. Thực thi những code paths sử dụng API đã công bố.

### Bước 6 — Chạy source compile tests

Biên dịch lại consumer source với candidate để phát hiện source incompatibilities. Không dùng kết quả này thay cho bước 5.

### Bước 7 — Chạy behavioral regression

Kiểm output, exception, validation, database, serialization, security và concurrency theo hợp đồng consumer.

### Bước 8 — Kiểm dependency graph và môi trường

Xác minh runtime đang tải đúng library/JDK/OS/class loader. Tách lỗi binary API khỏi lỗi version bytecode hoặc native dependencies.

### Bước 9 — Phân loại breaking changes

Với mỗi break, quyết định giữ bridge, cung cấp adapter, phát hành major version hay yêu cầu consumer rebuild. Ghi consumer owner và kế hoạch rollout.

### Bước 10 — Quyết định phát hành

Chỉ đánh dấu tương thích khi các gate tương ứng có bằng chứng. Công bố version, changelog, migration guide, known incompatibilities và phương án rollback khi cần.

## 34. Những hiểu lầm phổ biến

**“Source vẫn compile thì binary cũ chắc chắn chạy.”** Sai. Bài đã mô tả `int → long`: source compile lại được nhưng original bytecode vẫn gọi descriptor cũ.

**“JVM sẽ tự widening từ int sang long khi liên kết method cũ.”** Không. Widening ở bước Java compiler overload resolution không thay thế symbolic method reference cố định trong bytecode.

**“NoSuchMethodError luôn do thiếu class.”** Không. Class có thể tồn tại nhưng thiếu đúng method descriptor cần thiết.

**“Rebuild consumer thành công nghĩa là library không breaking.”** Chỉ chứng minh consumer source có thể được cập nhật/biên dịch; artifact cũ vẫn có thể hỏng.

**“Giữ tên method là đủ.”** Không. Tham số, return descriptor, static/instance và accessibility có thể quyết định linkage.

**“Thêm `@Deprecated` làm consumer cũ không còn gọi được method.”** Không. Deprecated là tín hiệu cho compiler/tài liệu; method vẫn tồn tại nếu không bị xóa.

**“Thêm overload luôn bảo đảm mọi source consumer tương thích.”** Không. Một overload mới có thể làm overload resolution ambiguous hoặc chọn method khác khi compile lại.

**“Đổi major version thì runtime tự hiểu API cũ.”** Không. Version là hợp đồng phát hành, JVM vẫn cần class/method thực tế.

**“Có cả v1 và v2 trên classpath sẽ bảo đảm mọi consumer dùng đúng bản của mình.”** Không. Trùng class cùng loader là rủi ro, không phải một compatibility layer.

**“Chỉ cần API diff PASS, không cần runtime test.”** API diff rất hữu ích nhưng không xác nhận behavior, class loading hoặc mọi integration path.

**“Vì cùng JDK nên binary chắc chắn tương thích.”** Không. JDK và library ABI là hai trục khác nhau.

**“Giữ compatibility bridge thì behavior không thể đổi.”** Không. Bridge có thể delegate tới logic mới với semantics khác, nên vẫn cần contract tests.

## 35. Checklist dành cho người bảo trì thư viện

- [ ] Đã xác định consumers nào có thể dùng binary JAR cũ.
- [ ] Đã lưu catalog-core v1 và original consumer JAR, cùng checksum.
- [ ] Đã xác minh consumer original được biên dịch với method `formatPrice(int)`.
- [ ] Đã build v2 độc lập, không trộn class v1 vào v2 JAR.
- [ ] Đã tái hiện lỗi bằng original consumer + v2.
- [ ] Đã dùng `javap` xác định descriptor `(I)Ljava/lang/String;`.
- [ ] Đã kiểm v2 chỉ có descriptor `(J)Ljava/lang/String;`.
- [ ] Đã phân biệt source recompilation với binary runtime test.
- [ ] Đã giữ compatibility overload/bridge khi hợp đồng yêu cầu.
- [ ] Đã chạy original consumer + v2-fixed mà không rebuild consumer.
- [ ] Đã kiểm output/hành vi nghiệp vụ, không chỉ hết exception.
- [ ] Đã kiểm runtime chỉ tải đúng một library version.
- [ ] Đã xem dependency graph và class loader khi có nhiều artifacts.
- [ ] Đã nêu Java minimum runtime và class-file version.
- [ ] Đã xem xét API diff và binary tests như release gates.
- [ ] Đã phân loại breaking change, SemVer và consumer migration policy.
- [ ] Đã ghi JDK/vendor/build, artifacts, checksums và logs trong báo cáo.
- [ ] Đã có owner, changelog, rollout và rollback/roll-forward plan nếu đây là thư viện production.

## 36. Tài liệu tham khảo nền tảng

Nếu cần tra cứu quy tắc chính thức về tương thích và liên kết:

- **Java Language Specification, Chapter 13 — Binary Compatibility:** https://docs.oracle.com/javase/specs/jls/se21/html/jls-13.html
- **Java Virtual Machine Specification, Chapter 4 — Class File Format:** https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html
- **Java Virtual Machine Specification, Chapter 5 — Loading, Linking, and Initializing:** https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html
- **JDK `javap` command:** https://docs.oracle.com/en/java/javase/21/docs/specs/man/javap.html
- **JDK `jar` command:** https://docs.oracle.com/en/java/javase/21/docs/specs/man/jar.html
- **JDK `javac` command:** https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html

Các đường dẫn trên dùng Java 21 làm tài liệu tham khảo ổn định cho khái niệm. Khi dự án dùng JDK khác, hãy đối chiếu command syntax và runtime support theo release thực tế.

## Kết luận

**Một thư viện mới có thể làm hỏng artifact consumer cũ dù source consumer vẫn biên dịch lại thành công.** Khi thay `PriceService.formatPrice(int)` bằng `formatPrice(long)` mà không giữ overload cũ, consumer JAR đã biên dịch vẫn gọi descriptor `(I)Ljava/lang/String;` và có thể gặp `NoSuchMethodError`. Điều này chứng minh **tương thích nguồn không bảo đảm tương thích nhị phân**.

Quy trình xử lý đúng là giữ nguyên artifact consumer để tái hiện, dùng `javap` xác nhận method descriptor, kiểm classpath thực tế, rồi sửa library bằng bridge hoặc thực hiện migration breaking-change có chủ đích. Sau khi sửa, phải **chạy lại chính consumer artifact cũ**, đồng thời kiểm hợp đồng hành vi và môi trường JDK mục tiêu. Đưa API/ABI diff cùng binary consumer tests vào pipeline phát hành sẽ giúp phát hiện sự cố ngay tại library release thay vì đợi các service/plugin phía sử dụng thất bại ở runtime.
