# Thu hẹp quyền truy cập và ảnh hưởng đến mã đã biên dịch

Khi một thư viện Java được phát hành, các ứng dụng khác có thể đã biên dịch mã nguồn thành file `.class` và lưu trữ những file này trong JAR. Nếu nhà cung cấp thay đổi một method từ `public` thành `protected`, package-private hoặc `private`, mã nguồn của ứng dụng có thể không còn biên dịch được. Ngay cả khi không biên dịch lại, ứng dụng đã có cũng có thể lỗi khi chạy.

Nguyên nhân là quyền truy cập không chỉ được kiểm tra bởi compiler. JVM cũng thực hiện kiểm tra quyền truy cập khi phân giải các tham chiếu class, field và method trong bytecode. Việc thu hẹp quyền truy cập có thể giữ nguyên tên method và descriptor nhưng làm cho một binary đã biên dịch không còn quyền gọi thành phần đó. Lỗi thường gặp là `IllegalAccessError`, thuộc nhóm `LinkageError`.

Để đánh giá tương thích nhị phân, cần xem ai đang truy cập thành phần, từ package nào, có quan hệ kế thừa hay không và module có export package đó không. Sau đó cần kiểm tra cả source consumer mới lẫn binary consumer đã phát hành.

## 1. Các mức truy cập trong Java

Java có bốn mức truy cập thường dùng: `public`, `protected`, package-private (không ghi modifier) và `private`. Mỗi mức xác định những mã nguồn nào có thể truy cập thành viên hoặc kiểu được khai báo.

| Mức truy cập | Cùng class | Cùng package | Subclass ở package khác | Class không liên quan ở package khác |
|---|---:|---:|---:|---:|
| `public` | Có | Có | Có | Có, nếu các điều kiện module/package cũng cho phép |
| `protected` | Có | Có | Có, theo quy tắc truy cập protected | Không |
| package-private | Có | Có | Không, nếu subclass ở package khác | Không |
| `private` | Có, bao gồm nestmate theo quy tắc Java | Không | Không | Không |

Với `protected`, quy tắc truy cập từ subclass ở package khác có điều kiện chi tiết hơn việc chỉ là subclass. Trong ngữ cảnh mã instance, biểu thức truy cập phải đáp ứng quy tắc protected access của Java; không phải subclass ở package khác có thể dùng quyền protected để truy cập tùy ý mọi instance của superclass.

Ví dụ:

```java
package library;

public class Account {
    public String id;
    protected void calculateInterest() {}
    void refreshCache() {}
    private void validateInternalState() {}
}
```

Một class ở package `library` có thể truy cập các thành viên package-private và protected theo quy tắc thông thường. Một class ở package khác chỉ truy cập trực tiếp thành viên public, hoặc thành viên protected trong trường hợp nó thỏa các quy tắc subclass.

### 1.1. Thu hẹp quyền truy cập là thay đổi theo hướng nào?

Có thể hình dung thứ tự mức truy cập từ rộng đến hẹp như sau:

```text
public
  |
  v
protected
  |
  v
package-private
  |
  v
private
```

Thay đổi theo chiều đi xuống có thể loại bỏ quyền truy cập mà consumer trước đây đang sử dụng. Thay đổi theo chiều đi lên thường mở rộng tập consumer được phép truy cập.

Không nên hiểu sơ đồ này là mọi cặp mức đều có thể thay đổi tự do trong mọi ngữ cảnh. Ví dụ, method override không được giảm quyền truy cập so với method bị override; compiler sẽ từ chối source vi phạm quy tắc đó. Tuy nhiên, việc thay đổi modifier của một thành viên trong thư viện đã phát hành vẫn có thể ảnh hưởng đến các subclass hoặc client đã biên dịch từ trước.

### 1.2. Quyền truy cập của class, constructor và member

Quyền truy cập có thể được thay đổi ở nhiều vị trí:

- **Top-level class:** một class public có thể được tham chiếu từ package khác; class top-level không public chỉ truy cập được trong package.
- **Nested class:** nested class có thể có các modifier truy cập, và việc thu hẹp quyền có thể làm client không còn tạo hoặc tham chiếu kiểu đó.
- **Constructor:** constructor public cho phép client tạo instance; đổi thành protected, package-private hoặc private có thể chặn lệnh `new` đã biên dịch.
- **Method:** client có thể mất quyền gọi method dù tên, tham số và kiểu trả về vẫn giữ nguyên.
- **Field:** bytecode cũ có thể không còn đọc hoặc ghi được field sau khi modifier bị thu hẹp.

Khi thay đổi một API, cần kiểm tra toàn bộ bề mặt công khai của nó, không chỉ các method nghiệp vụ chính.

## 2. Vì sao thu hẹp quyền truy cập có thể phá vỡ binary?

Compiler và JVM kiểm tra quyền truy cập ở hai thời điểm khác nhau.

Khi biên dịch, compiler đọc source code cùng API của thư viện. Nếu method không còn public và client không có quyền truy cập theo quy tắc Java, compiler báo lỗi. Đây là lỗi source compatibility.

Khi chạy, JVM nạp class file đã được biên dịch trước đó. Bytecode chứa các tham chiếu biểu tượng đến class, field hoặc method, bao gồm tên và descriptor. JVM tìm thành phần tương ứng và thực hiện kiểm tra truy cập. Nếu thành phần tồn tại nhưng binary gọi nó từ vị trí không còn được phép, JVM có thể ném `IllegalAccessError`.

Điểm quan trọng là access flags nằm trong metadata của class file; chúng không phải một phần của method descriptor. Vì thế, việc giữ nguyên tên method và descriptor không đủ để bảo đảm binary cũ tiếp tục gọi được method đó.

### 2.1. Ví dụ: đổi method public thành protected

Giả sử phiên bản 1 của thư viện có:

```java
package com.example.api;

public class ReportService {
    public void exportReport() {
        System.out.println("Exporting report");
    }
}
```

Một ứng dụng ở package khác gọi method:

```java
package com.example.client;

import com.example.api.ReportService;

public class Client {
    public static void main(String[] args) {
        new ReportService().exportReport();
    }
}
```

Client được biên dịch thành công với phiên bản 1. Bytecode của nó có tham chiếu đến `ReportService.exportReport:()V`.

Trong phiên bản 2, nhà cung cấp thu hẹp quyền truy cập:

```java
package com.example.api;

public class ReportService {
    protected void exportReport() {
        System.out.println("Exporting report");
    }
}
```

Nếu biên dịch lại `Client` với phiên bản 2, compiler báo lỗi vì client ở package khác và không phải subclass có quyền truy cập protected method theo quy tắc Java.

Nếu giữ nguyên file `Client.class` được biên dịch với phiên bản 1 rồi chạy cùng JAR phiên bản 2, JVM có thể ném lỗi tại thời điểm lời gọi được phân giải/thực hiện:

```text
java.lang.IllegalAccessError:
  class com.example.client.Client tried to access
  method com.example.api.ReportService.exportReport()
```

Tên method, tham số và kiểu trả về không đổi. Binary vẫn tìm được method nhưng không còn quyền truy cập. Đây là ví dụ một thay đổi có thể phá vỡ tương thích nhị phân dù chữ ký method vẫn giữ nguyên.

### 2.2. Thu hẹp quyền truy cập của field

Giả sử thư viện có field public:

```java
package com.example.api;

public class Settings {
    public String region = "ap-southeast-1";
}
```

Client có thể đọc trực tiếp:

```java
String region = new Settings().region;
```

Nếu phiên bản sau đổi field thành private:

```java
public class Settings {
    private String region = "ap-southeast-1";

    public String getRegion() {
        return region;
    }
}
```

Source client cũ không còn biên dịch được vì field không thể truy cập. Binary cũ vẫn tham chiếu đến field có tên và descriptor cũ, nhưng khi JVM kiểm tra quyền truy cập, lệnh đọc field có thể thất bại với `IllegalAccessError`.

Việc thêm getter mới không tự sửa binary đã phát hành. Binary cũ đã được biên dịch để đọc field trực tiếp; nó không tự chuyển lời gọi sang `getRegion()`. Consumer cần được biên dịch lại hoặc nhà cung cấp cần giữ một bề mặt tương thích trong thời gian chuyển đổi.

### 2.3. Thu hẹp quyền truy cập của constructor hoặc class

Constructor cũng là member có quyền truy cập. Nếu một class từng cung cấp constructor public và sau đó đổi thành protected hoặc private, client cũ đã biên dịch lệnh `new` có thể gặp `IllegalAccessError` khi JVM kiểm tra quyền gọi constructor.

Tương tự, đổi một top-level class từ public thành package-private có thể làm các binary bên ngoài package không còn quyền sử dụng class đó. Việc giữ nguyên tên class và file class không có nghĩa mọi consumer cũ vẫn truy cập được.

Với nested class, cần kiểm tra cả quyền của class chứa và nested class. Một client có thể mất quyền truy cập dù nested class vẫn tồn tại trong JAR.

## 3. Các lỗi có thể xuất hiện khi quyền truy cập bị thu hẹp

Thông báo cụ thể phụ thuộc vào loại thành phần, thời điểm JVM phân giải tham chiếu và đường chạy của ứng dụng. Những trường hợp thường gặp gồm:

| Thành phần bị thu hẹp | Tình huống của binary cũ | Lỗi có thể gặp |
|---|---|---|
| Public method | Client ngoài package tiếp tục gọi method đã đổi thành protected/private/package-private | `IllegalAccessError` |
| Public field | Client ngoài phạm vi quyền tiếp tục đọc/ghi field | `IllegalAccessError` |
| Public constructor | Client tiếp tục tạo instance bằng constructor đã bị thu hẹp | `IllegalAccessError` |
| Public class hoặc nested type | Binary bên ngoài tiếp tục tham chiếu kiểu không còn public | `IllegalAccessError` trong quá trình phân giải/truy cập kiểu |
| Package export trong module | Module client tham chiếu package không còn được export cho nó | Lỗi truy cập liên kết, thường là `IllegalAccessError` |
| Quyền reflection | Framework dùng reflection để tìm hoặc gọi thành viên không còn truy cập theo cách cũ | `NoSuchMethodException`, `IllegalAccessException` hoặc lỗi liên quan module như `InaccessibleObjectException`, tùy thao tác |

`IllegalAccessError` là một `LinkageError`, khác với lỗi compile `cannot access` hoặc `has protected access`. Đây cũng khác với `NoSuchMethodError`: lỗi này thường có nghĩa JVM không tìm thấy method với tên và descriptor mà binary yêu cầu. Khi thu hẹp quyền truy cập nhưng giữ nguyên member, vấn đề thường là member được tìm thấy nhưng quyền truy cập không còn hợp lệ.

Không phải mọi lỗi đều xuất hiện ngay lúc ứng dụng khởi động. JVM có thể phân giải tham chiếu khi đường chạy tương ứng được thực hiện. Do đó, một ứng dụng khởi động thành công vẫn có thể thất bại khi gọi một API ít dùng.

## 4. Phân biệt quyền truy cập Java với quyền truy cập module

Từ Java 9, hệ thống module bổ sung một lớp kiểm soát khả năng đọc module và truy cập package được export/open. Một class hoặc method có modifier `public` vẫn có thể không truy cập được từ module khác nếu package chứa nó không được export phù hợp.

Ví dụ trong `module-info.java`:

```java
module com.example.library {
    exports com.example.api;
}
```

Module client cần đọc module thư viện và package API cần được export. Nếu nhà cung cấp bỏ dòng `exports` hoặc chuyển package sang một module không được client đọc, binary cũ có thể gặp lỗi truy cập khi liên kết hoặc sử dụng kiểu public đó.

### 4.1. `exports` và `opens` có mục đích khác nhau

- `exports` cho phép module khác truy cập các kiểu public trong package được export theo quy tắc module.
- `opens` cho phép truy cập sâu bằng reflection vào package, bao gồm các thành viên không public trong phạm vi được cho phép.

Hai cơ chế này không thay thế nhau. Một framework gọi API public thông thường cần package được export. Framework dùng reflection để truy cập field private có thể cần package được open. Việc chỉ thêm `opens` không tự làm cho mọi lời gọi bytecode thông thường trở nên hợp lệ.

Các tùy chọn JVM như `--add-exports` và `--add-opens` có thể dùng làm biện pháp chuyển tiếp có kiểm soát trong những tình huống tương ứng. `--add-exports` hỗ trợ truy cập kiểu public trong package được chỉ định; `--add-opens` hỗ trợ deep reflection. Chúng không nên được dùng để che giấu một API nội bộ hoặc quyền truy cập đã bị thu hẹp mà không có kế hoạch migration.

### 4.2. Quyền truy cập reflection có thể thay đổi độc lập

Framework có thể tìm thành viên bằng reflection. Ví dụ:

```java
Method method = ReportService.class.getMethod("exportReport");
```

`getMethod` tìm public method, kể cả method public được kế thừa. Nếu method đổi thành protected, lời gọi tìm kiếm này có thể không còn tìm thấy method và ném `NoSuchMethodException`.

`getDeclaredMethod` tìm method được khai báo trực tiếp trong class mà không giới hạn ở public:

```java
Method method = ReportService.class.getDeclaredMethod("exportReport");
```

Tuy nhiên, tìm thấy method không có nghĩa là có thể gọi nó. `Method.invoke` vẫn phải đáp ứng quy tắc truy cập; `setAccessible(true)` hoặc `trySetAccessible()` còn chịu ảnh hưởng của module system và các giới hạn truy cập sâu. Vì vậy, thay đổi modifier có thể làm hỏng framework ORM, serializer, dependency injection hoặc mapper dù code ứng dụng không gọi method trực tiếp.

## 5. Thu hẹp quyền truy cập ảnh hưởng đến những consumer nào?

Không phải mọi binary đều bị ảnh hưởng giống nhau. Cần xác định vị trí truy cập và quan hệ giữa consumer với API.

### 5.1. Consumer ở cùng package

Nếu một public member đổi thành package-private, consumer ở cùng package vẫn có thể truy cập theo quy tắc Java, với điều kiện chúng thực sự thuộc cùng runtime package. Runtime package được xác định không chỉ bằng tên package mà còn bởi class loader. Hai class cùng tên package nhưng được nạp bởi class loader khác nhau có thể không thuộc cùng runtime package.

Vì vậy, kiểm tra source chỉ nhìn thấy dòng `package` đôi khi chưa đủ trong ứng dụng có plugin hoặc class loader tùy chỉnh.

### 5.2. Subclass ở package khác

Nếu public method đổi thành protected, một subclass ở package khác vẫn có thể có quyền truy cập trong ngữ cảnh hợp lệ. Nhưng các client không phải subclass sẽ mất quyền. Ngay cả trong subclass, protected access có quy tắc về kiểu của receiver; không thể coi protected là tương đương public.

Ví dụ:

```java
package com.example.extension;

import com.example.api.ReportService;

public class CustomReportService extends ReportService {
    public void runExport() {
        exportReport(); // Có thể truy cập protected qua kế thừa.
    }
}
```

Việc client subclass vẫn chạy không chứng minh tất cả consumer đều tương thích. Cần kiểm tra cả các lời gọi trực tiếp từ class không kế thừa.

### 5.3. Consumer sử dụng reflection hoặc framework

Các framework có thể dựa vào public constructor, public getter/setter hoặc truy cập sâu bằng reflection. Khi modifier thay đổi, lỗi có thể chỉ xuất hiện lúc framework khởi tạo bean, ánh xạ entity, serialize dữ liệu hoặc nạp plugin.

Không nên chỉ tìm các lời gọi method tĩnh trong source. Hãy tìm cấu hình tên class/method, annotation, XML mapping, reflection và các thư viện tự động quét classpath.

## 6. Vì sao nhà cung cấp muốn thu hẹp quyền truy cập?

Việc giảm mức truy cập thường nhằm kiểm soát bề mặt API và giảm số hợp đồng mà nhà cung cấp phải duy trì lâu dài. Một method public có thể bị nhiều ứng dụng phụ thuộc, khiến nhà cung cấp khó thay đổi cấu trúc bên trong.

Các lý do phổ biến:

- **Ẩn chi tiết triển khai:** chuyển helper method hoặc field thành private/package-private để consumer không phụ thuộc vào nội bộ.
- **Bảo vệ bất biến dữ liệu:** tránh client sửa trực tiếp field làm object rơi vào trạng thái không hợp lệ.
- **Kiểm soát điểm mở rộng:** giữ một số hook ở protected thay vì public để giới hạn cách subclass tương tác.
- **Đóng gói module:** chỉ export những package được xem là API hỗ trợ chính thức.
- **Loại bỏ API không còn được hỗ trợ:** giảm bề mặt tương thích sau một giai đoạn deprecated hoặc chuyển đổi.
- **Giảm rủi ro bảo mật:** hạn chế truy cập vào dữ liệu hoặc thao tác nội bộ nhạy cảm.

Đây có thể là cải tiến thiết kế hợp lý, nhưng nếu API đã được phát hành và có consumer bên ngoài, thay đổi vẫn cần được quản lý như một thay đổi tương thích có tác động.

## 7. Cách thu hẹp quyền truy cập mà giảm rủi ro migration

Nếu nhà cung cấp kiểm soát được thư viện và các consumer, có thể thực hiện theo từng giai đoạn.

### 7.1. Xác định bề mặt API đang được sử dụng

Trước tiên, liệt kê class, constructor, method và field public/protected. Kết hợp phân tích API với dữ liệu sử dụng thực tế, source consumer, plugin và tài liệu tích hợp. Phân biệt API được công bố hỗ trợ với chi tiết nội bộ vô tình bị lộ.

Các công cụ như Revapi hoặc japicmp có thể so sánh hai phiên bản thư viện và chỉ ra thay đổi modifier có khả năng phá vỡ tương thích. Kết quả cần được đọc cùng ngữ cảnh consumer vì công cụ không biết toàn bộ cách ứng dụng sử dụng reflection hoặc class loader.

### 7.2. Đánh dấu deprecated trước khi thu hẹp hoặc loại bỏ

Nếu một public method cần được thay thế, có thể giữ nó trong một giai đoạn và đánh dấu deprecated:

```java
public class ReportService {
    /**
     * @deprecated Use {@link #export()} instead.
     */
    @Deprecated(since = "2.4", forRemoval = true)
    public void exportReport() {
        export();
    }

    public void export() {
        // Implementation mới
    }
}
```

Giữ method cũ và delegate sang method mới giúp binary cũ tiếp tục gọi được trong thời gian chuyển tiếp. Sau đó, thông báo rõ phiên bản dự kiến loại bỏ và cung cấp hướng dẫn thay thế.

Lưu ý: đánh dấu deprecated không tự thu hẹp quyền truy cập. Đây là bước thông báo để consumer có thời gian chuyển đổi trước khi nhà cung cấp thực hiện thay đổi phá vỡ tương thích ở phiên bản major phù hợp.

### 7.3. Giữ facade public và chuyển logic vào implementation nội bộ

Một cách giảm bề mặt API là giữ method public ổn định nhưng chuyển logic sang thành phần nội bộ:

```java
public class ReportService {
    private final ReportExporter exporter = new ReportExporter();

    public void export() {
        exporter.export();
    }
}

final class ReportExporter {
    void export() {
        // Chi tiết triển khai nội bộ
    }
}
```

Client tiếp tục gọi facade public, trong khi implementation có thể được thay đổi mà không phơi bày helper method. Cách này thường phù hợp hơn việc đổi hàng loạt method public đã phát hành thành private trong một bản cập nhật nhỏ.

### 7.4. Phát hành thay đổi phá vỡ trong phiên bản major có kế hoạch

Nếu phải thu hẹp hoặc loại bỏ API public, hãy công bố rõ thay đổi trong release notes và migration guide, nêu API cũ, API thay thế, thời điểm loại bỏ và lỗi có thể xuất hiện. Với thư viện được nhiều ứng dụng sử dụng, cần có thời gian chuyển tiếp và ví dụ migration.

Phiên bản major không tự làm thay đổi trở nên an toàn. Nó chỉ là tín hiệu versioning giúp consumer biết hợp đồng có thể đã thay đổi. Vẫn cần kiểm tra binary compatibility và có kế hoạch triển khai các consumer phụ thuộc.

### 7.5. Cân nhắc adapter hoặc bridge khi cần hỗ trợ binary cũ

Trong một số trường hợp, có thể giữ lại method public cũ dưới dạng bridge method, delegate đến implementation mới. Điều này cho phép consumer cũ tiếp tục hoạt động trong thời gian chuyển đổi.

Không phải lúc nào cũng có thể giữ bridge: có thể có lý do bảo mật, bất biến hoặc thay đổi mô hình dữ liệu khiến API cũ không còn an toàn. Khi không thể giữ, cần thông báo breaking change rõ ràng và yêu cầu consumer biên dịch lại.

## 8. Kiểm tra ảnh hưởng đến source và binary đã biên dịch

Một migration cần hai loại kiểm tra riêng. Biên dịch lại source consumer xác nhận source compatibility; chạy artifact cũ với thư viện mới giúp phát hiện vấn đề binary linkage.

### 8.1. Biên dịch source consumer với thư viện mới

Giữ một consumer đại diện hoặc bộ kiểm thử tương thích API. Biên dịch nó với phiên bản thư viện mới. Các lỗi như `has protected access`, `is not public` hoặc `cannot access` cho thấy source đang sử dụng quyền truy cập đã bị thu hẹp.

Kiểm tra các trường hợp:

- Client bên ngoài package gọi public member.
- Subclass ở package khác override hoặc gọi protected member.
- Client khởi tạo class bằng constructor đã thay đổi modifier.
- Code truy cập field trực tiếp.
- Reflection hoặc framework tìm public member.
- Module client đọc và truy cập package đã thay đổi export.

### 8.2. Chạy binary cũ với thư viện mới

Để kiểm tra binary compatibility, quy trình cần giữ nguyên artifact consumer đã biên dịch với thư viện cũ:

```text
Thư viện phiên bản 1
        |
        v
Biên dịch Client.java
        |
        v
Giữ nguyên Client.class
        |
        v
Thay thư viện bằng phiên bản 2
        |
        v
Chạy Client.class cũ với thư viện mới
        |
        v
Quan sát lỗi liên kết/truy cập
```

Ví dụ lệnh tổng quát:

```bash
# Compile consumer với API cũ
javac -cp library-v1.jar -d consumer-classes Client.java

# Chạy bytecode cũ với API mới
java -cp library-v2.jar:consumer-classes com.example.client.Client
```

Trên Windows, ký tự phân tách classpath là dấu chấm phẩy (`;`) thay vì dấu hai chấm (`:`). Quan trọng là không biên dịch lại `Client.class` giữa hai bước; nếu compile lại với thư viện mới, lỗi source sẽ xuất hiện trước khi kiểm tra được binary cũ.

### 8.3. Kiểm tra cả đường chạy ít được sử dụng

Một binary có thể khởi động thành công vì JVM chưa phân giải mọi tham chiếu. Cần gọi các method và nhánh nghiệp vụ sử dụng API bị thay đổi, khởi tạo các class liên quan và chạy plugin/reflection path.

Nếu thư viện được dùng bởi nhiều phiên bản ứng dụng, hãy thử các artifact consumer quan trọng hoặc duy trì bộ kiểm thử binary compatibility tự động.

### 8.4. Kiểm tra module và reflection

Nếu ứng dụng dùng module path, chạy thử với `module-info.java` và cấu hình exports thực tế. Nếu framework dùng reflection, tạo integration test để xác nhận việc tìm method/field, truy cập constructor và gọi `setAccessible`/`trySetAccessible` trong môi trường module mục tiêu.

Không nên chỉ chạy test trên classpath nếu production triển khai trên module path, vì quy tắc module có thể làm thay đổi kết quả truy cập.

## 9. Cách đọc lỗi và khoanh vùng nguyên nhân

Khi một ứng dụng cũ lỗi sau khi thay thư viện, hãy phân biệt lỗi truy cập với lỗi thiếu member hoặc lỗi cấu trúc class.

| Thông báo | Diễn giải | Hướng kiểm tra |
|---|---|---|
| `IllegalAccessError` | Member/class được tìm thấy nhưng binary không có quyền truy cập | So sánh modifier, package, subclass relationship và module exports. |
| `NoSuchMethodError` | Không tìm thấy method có tên và descriptor mà bytecode yêu cầu | So sánh API cũ/mới, overload, kiểu tham số/trả về và dependency được nạp. |
| `NoSuchFieldError` | Không tìm thấy field có tên và descriptor mà bytecode yêu cầu | Kiểm tra field bị đổi tên, xóa hoặc đổi kiểu. |
| `ClassNotFoundException` | Code chủ động nạp class bằng tên nhưng class loader không tìm thấy | Kiểm tra classpath/module path, tên class và class loader. |
| `NoClassDefFoundError` | JVM không thể cung cấp class cần thiết khi liên kết hoặc sử dụng | Kiểm tra JAR thiếu, dependency bắc cầu hoặc lỗi khởi tạo class trước đó. |
| `IllegalAccessException` | Reflection không được phép thực hiện thao tác | Kiểm tra modifier, caller và quyền reflection. |
| `InaccessibleObjectException` | Deep reflection bị chặn bởi quy tắc encapsulation/module | Kiểm tra package có được open và chính sách module. |

Một stack trace có thể chỉ đến framework thay vì dòng code ứng dụng. Hãy tìm class và method thực sự bị truy cập, sau đó xác định ai gọi nó và class loader/module nào tham gia.

## 10. Những nhầm lẫn thường gặp

**“Tên method và descriptor không đổi nên binary vẫn tương thích.”** Descriptor chỉ xác định method ở mức liên kết. Access flags vẫn được JVM kiểm tra; binary cũ có thể gặp `IllegalAccessError`.

**“Đổi public thành protected chỉ ảnh hưởng code biên dịch lại.”** Source consumer có thể báo lỗi ngay khi compile, nhưng binary cũ cũng có thể thất bại khi JVM kiểm tra quyền truy cập.

**“Thêm getter mới sẽ giữ tương thích cho client đọc field cũ.”** Binary cũ vẫn tham chiếu trực tiếp đến field. Nó không tự chuyển sang getter mới.

**“Protected tương đương public đối với mọi subclass.”** Protected có quy tắc truy cập cụ thể, đặc biệt với subclass ở package khác và kiểu của receiver.

**“Method public thì module nào cũng gọi được.”** JPMS còn kiểm soát readability và exports. Một kiểu public trong package không được export có thể không truy cập được từ module khác.

**“Ứng dụng khởi động thành công là đủ.”** Tham chiếu có thể chỉ được phân giải khi một luồng nghiệp vụ, plugin hoặc reflection path được thực thi.

## 11. Checklist khi thu hẹp quyền truy cập trong thư viện

- [ ] Đã xác định member/class/constructor nào sẽ giảm quyền truy cập.
- [ ] Đã tìm các consumer ngoài package và subclass đang sử dụng API.
- [ ] Đã kiểm tra binary đã phát hành, plugin và ứng dụng không thể build lại đồng thời.
- [ ] Đã kiểm tra reflection, framework mapping và cấu hình nạp class động.
- [ ] Đã xem xét module `exports`/`opens` và module path production.
- [ ] Đã đánh giá lỗi có thể xuất hiện, đặc biệt `IllegalAccessError`.
- [ ] Đã cân nhắc giữ facade/bridge hoặc giai đoạn deprecated trước khi thu hẹp.
- [ ] Đã công bố breaking change và hướng migration nếu không thể giữ API cũ.
- [ ] Đã biên dịch source consumer với thư viện mới.
- [ ] Đã chạy binary consumer cũ với thư viện mới mà không biên dịch lại artifact.
- [ ] Đã kiểm tra các nhánh runtime, plugin và reflection ít được sử dụng.
- [ ] Đã lưu kết quả kiểm thử và phiên bản thư viện/JDK dùng để xác minh.

## 12. Kết luận

Thu hẹp quyền truy cập từ `public` xuống `protected`, package-private hoặc `private` có thể phá vỡ tương thích nhị phân. Dù tên class, field hoặc method và descriptor vẫn giữ nguyên, JVM vẫn kiểm tra access flags khi phân giải và sử dụng tham chiếu từ bytecode. Nếu binary cũ gọi một thành viên mà nó không còn quyền truy cập, lỗi `IllegalAccessError` có thể xuất hiện tại runtime.

Ảnh hưởng còn phụ thuộc vào package, quan hệ kế thừa, class loader, module exports và việc ứng dụng dùng reflection hay framework tự động. Vì vậy, nhà cung cấp nên kiểm kê consumer, thông báo deprecated, giữ facade hoặc bridge khi phù hợp và công bố breaking change có kế hoạch. Việc xác minh phải gồm cả biên dịch lại source consumer lẫn chạy artifact cũ với thư viện mới. Chỉ khi các trường hợp truy cập liên quan đã được kiểm chứng, nhóm mới có thể đánh giá chính xác mức độ an toàn của thay đổi quyền truy cập.
