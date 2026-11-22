# Cấu hình dung lượng bằng `DataSize` và `@DataSizeUnit` trong Spring Boot

## 1. Vấn đề: dung lượng không chỉ là một con số

Trong Spring Boot, nhiều thuộc tính cấu hình biểu diễn **dung lượng dữ liệu**: kích thước file tải lên tối đa, giới hạn một bộ đệm, ngưỡng dữ liệu giữ trong bộ nhớ, hoặc giới hạn dung lượng cho một thao tác.

Nếu chỉ dùng `long` hoặc `int`, cấu hình như sau thường thiếu ngữ cảnh:

~~~yaml
app:
  storage:
    upload-buffer: 8
    max-object-size: 64
~~~

Các số `8` và `64` là **byte**, **kilobyte** hay **megabyte**? Người triển khai có thể hiểu khác tác giả và vô tình tạo ra một bộ đệm quá nhỏ hoặc một giới hạn quá lớn.

Spring Framework cung cấp kiểu `org.springframework.util.unit.DataSize` để biểu diễn kích thước theo số **byte**. Spring Boot hỗ trợ chuyển đổi chuỗi cấu hình sang `DataSize` khi bind `@ConfigurationProperties`, với các cách viết rõ đơn vị như:

~~~properties
app.storage.upload-buffer=8MB
app.storage.max-object-size=64MB
app.storage.memory-threshold=256KB
~~~

Khi cần một **đơn vị mặc định khác byte** cho giá trị không có hậu tố, Spring Boot cung cấp annotation `org.springframework.boot.convert.DataSizeUnit`:

~~~java
@DataSizeUnit(DataUnit.MEGABYTES)
private DataSize uploadBuffer;
~~~

Khi đó `app.storage.upload-buffer=8` được hiểu là **8MB** thay vì 8 byte. Nếu cấu hình viết rõ `512KB`, hậu tố `KB` mới là yếu tố quyết định đơn vị.

> Hai ý cần tách biệt: **`DataSize` là kiểu giá trị dung lượng**, còn **`@DataSizeUnit` xác định đơn vị mặc định khi giá trị cấu hình không ghi đơn vị**. Annotation không đặt giá trị mặc định cho một property bị thiếu.

## 2. `DataSize` và `DataUnit` là gì?

Các class liên quan:

~~~java
import org.springframework.util.unit.DataSize;
import org.springframework.util.unit.DataUnit;
import org.springframework.boot.convert.DataSizeUnit;
~~~

- `DataSize`: một value object bất biến biểu diễn dung lượng theo số byte; có các factory method như `ofBytes(...)`, `ofKilobytes(...)`, `ofMegabytes(...)`, `ofGigabytes(...)` và `ofTerabytes(...)`.
- `DataUnit`: enum xác định các đơn vị chuẩn mà `DataSize` hỗ trợ, gồm `BYTES`, `KILOBYTES`, `MEGABYTES`, `GIGABYTES` và `TERABYTES`.
- `@DataSizeUnit`: annotation của Spring Boot được áp dụng ở điểm binding để thay đổi đơn vị mặc định của một thuộc tính `DataSize` khi nguồn cấu hình chứa số không có hậu tố.

Ví dụ sử dụng trực tiếp trong Java:

~~~java
DataSize small = DataSize.ofBytes(512);
DataSize medium = DataSize.ofKilobytes(256);
DataSize large = DataSize.ofMegabytes(10);

long bytes = large.toBytes();
boolean tooBig = large.compareTo(DataSize.ofMegabytes(8)) > 0;
~~~

`DataSize` không tự biết đây là dung lượng đĩa, bộ đệm, dữ liệu HTTP hay kích thước file. Nó chỉ biểu diễn **một đại lượng dung lượng**, còn cách sử dụng và các giới hạn hợp lệ do ứng dụng xác định.

### 2.1. Đơn vị dùng hệ nhị phân

Dù hậu tố của API viết `KB`, `MB` và `GB`, các đơn vị trong `DataUnit` được định nghĩa theo **lũy thừa của 2**, không phải bội số 1.000.

| Đơn vị | Hậu tố | Số byte |
| --- | --- | ---: |
| Byte | `B` | 1 |
| Kilobyte | `KB` | 1.024 |
| Megabyte | `MB` | 1.048.576 |
| Gigabyte | `GB` | 1.073.741.824 |
| Terabyte | `TB` | 1.099.511.627.776 |

Ví dụ:

~~~java
DataSize oneKb = DataSize.ofKilobytes(1);
DataSize oneMb = DataSize.ofMegabytes(1);

System.out.println(oneKb.toBytes()); // 1024
System.out.println(oneMb.toBytes()); // 1048576
~~~

Điều này quan trọng khi đối chiếu với các hệ thống bên ngoài sử dụng quy ước SI (1 MB = 1.000.000 byte). Trong cấu hình Spring Boot `DataSize`, `1MB` ở đây là 1.048.576 byte. Nếu giao thức hoặc dịch vụ ngoài yêu cầu byte chính xác, nên chuyển sang `toBytes()` rồi dùng giá trị long đã quy đổi.

## 3. Các định dạng dung lượng được Spring Boot hỗ trợ

Khi bind vào thuộc tính `DataSize`, Spring Boot hiểu các chuỗi gồm số và hậu tố đơn vị được hỗ trợ:

~~~properties
app.storage.minimum=512B
app.storage.buffer=8KB
app.storage.cache=64MB
app.storage.quota=2GB
app.storage.archive=1TB
~~~

Đối với nguồn không có hậu tố:

~~~properties
app.storage.minimum=512
~~~

nếu property `minimum` có kiểu `DataSize` và **không có `@DataSizeUnit`**, số `512` được hiểu là **512 byte**.

Bảng minh họa:

| Giá trị cấu hình | Đơn vị được hiểu | Tổng số byte |
| --- | --- | ---: |
| `256` | `B` theo mặc định | 256 |
| `256B` | `B` | 256 |
| `2KB` | `KB` | 2.048 |
| `8MB` | `MB` | 8.388.608 |
| `1GB` | `GB` | 1.073.741.824 |
| `1TB` | `TB` | 1.099.511.627.776 |

Chọn cú pháp chuẩn **số nguyên liền với hậu tố**, ví dụ `256KB` hoặc `2MB`. Không nên giả định parser chấp nhận mọi cách viết tự do như `"2 MB"`, `"1.5MB"`, `"200 MiB"` hoặc tên đơn vị tùy chỉnh. Nếu cần một kích thước phân số, hãy chuyển nó sang một đơn vị nhỏ hơn và viết bằng số nguyên, ví dụ **`1.5MB` có thể được biểu diễn bằng `1536KB`** trong quy ước nhị phân.

Giá trị `0B` hoặc một số âm có thể biểu diễn được bởi kiểu `DataSize`, nhưng **điều đó không đồng nghĩa nó hợp lệ với mọi cấu hình nghiệp vụ**. Hãy kiểm tra giới hạn riêng cho bộ đệm, tệp tải lên và bộ nhớ.

## 4. Không có `@DataSizeUnit`: số trần mặc định là byte

Giả sử class của ứng dụng có:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.util.unit.DataSize;

@ConfigurationProperties(prefix = "app.storage")
public class StorageProperties {
    private DataSize memoryThreshold = DataSize.ofBytes(512);

    public DataSize getMemoryThreshold() {
        return memoryThreshold;
    }

    public void setMemoryThreshold(DataSize memoryThreshold) {
        this.memoryThreshold = memoryThreshold;
    }
}
~~~

Và YAML:

~~~yaml
app:
  storage:
    memory-threshold: 256
~~~

`memoryThreshold` được bind thành `DataSize.ofBytes(256)` vì **byte là đơn vị mặc định**.

So sánh:

~~~yaml
# Cấu hình A:
app:
  storage:
    memory-threshold: 256
~~~

~~~yaml
# Cấu hình B:
app:
  storage:
    memory-threshold: 256KB
~~~

Hai giá trị không tương đương: A là 256 byte, B là 262.144 byte. Sự khác biệt gấp 1.024 lần, nên bỏ hậu tố trong cấu hình dung lượng lớn có thể gây lỗi đáng kể.

**Khuyến nghị:** nếu cấu hình được người vận hành thường xuyên chỉnh sửa, ghi hậu tố `B`, `KB`, `MB` hoặc `GB` một cách tường minh để tránh hiểu nhầm, ngay cả khi Java đã có annotation đặt đơn vị mặc định.

## 5. Dùng `@DataSizeUnit` cho thuộc tính không có hậu tố

Giả sử các team thống nhất rằng mọi số không có hậu tố của `upload-buffer` đều tính theo megabyte. Ta có thể khai báo:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.convert.DataSizeUnit;
import org.springframework.util.unit.DataSize;
import org.springframework.util.unit.DataUnit;

@ConfigurationProperties(prefix = "app.storage")
public class StorageProperties {
    @DataSizeUnit(DataUnit.MEGABYTES)
    private DataSize uploadBuffer = DataSize.ofMegabytes(2);

    public DataSize getUploadBuffer() {
        return uploadBuffer;
    }

    public void setUploadBuffer(DataSize uploadBuffer) {
        this.uploadBuffer = uploadBuffer;
    }
}
~~~

Khi nguồn cấu hình có:

~~~properties
app.storage.upload-buffer=8
~~~

binder hiểu `8` là **8MB**, tức 8.388.608 byte.

Nếu cấu hình thay thành:

~~~properties
app.storage.upload-buffer=512KB
~~~

thì giá trị hiệu lực là **512KB**, tức 524.288 byte. Annotation `@DataSizeUnit(DataUnit.MEGABYTES)` **không ép mọi giá trị thành đơn vị MB bất chấp hậu tố**. Nó chỉ cung cấp đơn vị mặc định cho trường hợp không có hậu tố.

Một bảng ngắn:

| Dòng config | Annotation trên field | Kết quả |
| --- | --- | --- |
| `upload-buffer=8` | Không có | 8 byte |
| `upload-buffer=8` | `@DataSizeUnit(MEGABYTES)` | 8MB |
| `upload-buffer=8MB` | Không có | 8MB |
| `upload-buffer=8MB` | `@DataSizeUnit(MEGABYTES)` | 8MB |
| `upload-buffer=512KB` | `@DataSizeUnit(MEGABYTES)` | 512KB |

### 5.1. Annotation không phải giá trị mặc định

Hai đoạn dưới đây có trách nhiệm khác nhau:

~~~java
@DataSizeUnit(DataUnit.MEGABYTES)
private DataSize uploadBuffer;
~~~

Annotation định nghĩa **đơn vị khi có dữ liệu dạng số không hậu tố**. Nếu không có property `app.storage.upload-buffer` ở bất kỳ nguồn nào và không có initializer, field vẫn có thể là `null`.

~~~java
@DataSizeUnit(DataUnit.MEGABYTES)
private DataSize uploadBuffer = DataSize.ofMegabytes(2);
~~~

Ở đây `DataSize.ofMegabytes(2)` mới tạo ra giá trị mặc định **2MB** ngay khi object được tạo. Nếu binder không nhận một override nào cho field này, initializer có thể tiếp tục được giữ.

Nếu YAML có `upload-buffer: 8` thì binder ghi đè 2MB bằng 8MB; nếu YAML không khai báo `upload-buffer` thì field vẫn có thể là 2MB.

## 6. Ví dụ hoàn chỉnh: JavaBean `@ConfigurationProperties`

Giả sử ứng dụng quản lý ba giới hạn:

- `max-object-size`: kích thước object lớn nhất được chấp nhận.
- `upload-buffer`: kích thước buffer dành cho tác vụ xử lý upload.
- `memory-threshold`: ngưỡng giữ dữ liệu trong RAM trước khi dùng chiến lược khác.

### 6.1. Cấu hình YAML

~~~yaml
# src/main/resources/application.yml
app:
  storage:
    max-object-size: 64MB
    upload-buffer: 8
    memory-threshold: 256KB
~~~

Ở đây `upload-buffer: 8` cố ý **không có hậu tố** để minh họa `@DataSizeUnit`. Trong vận hành thật, `upload-buffer: 8MB` thường dễ hiểu hơn.

### 6.2. Class JavaBean

~~~java
package com.example.config;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.convert.DataSizeUnit;
import org.springframework.util.unit.DataSize;
import org.springframework.util.unit.DataUnit;

@ConfigurationProperties(prefix = "app.storage")
public class StorageProperties {
    private DataSize maxObjectSize = DataSize.ofMegabytes(32);

    @DataSizeUnit(DataUnit.MEGABYTES)
    private DataSize uploadBuffer = DataSize.ofMegabytes(2);

    private DataSize memoryThreshold = DataSize.ofBytes(512);

    public DataSize getMaxObjectSize() {
        return maxObjectSize;
    }

    public void setMaxObjectSize(DataSize maxObjectSize) {
        this.maxObjectSize = maxObjectSize;
    }

    public DataSize getUploadBuffer() {
        return uploadBuffer;
    }

    public void setUploadBuffer(DataSize uploadBuffer) {
        this.uploadBuffer = uploadBuffer;
    }

    public DataSize getMemoryThreshold() {
        return memoryThreshold;
    }

    public void setMemoryThreshold(DataSize memoryThreshold) {
        this.memoryThreshold = memoryThreshold;
    }
}
~~~

### 6.3. Đăng ký properties bean

Một cách đăng ký:

~~~java
package com.example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

Hoặc dùng `@EnableConfigurationProperties(StorageProperties.class)` trong một lớp cấu hình. Đừng vừa tạo bean thủ công vừa scan cùng type mà không có lý do vì có thể đăng ký nhiều bean không mong muốn.

### 6.4. Kết quả sau khi bind

| Field Java | Giá trị từ YAML | `toBytes()` |
| --- | --- | ---: |
| `maxObjectSize` | `64MB` | 67.108.864 |
| `uploadBuffer` | `8` với `@DataSizeUnit(MEGABYTES)` | 8.388.608 |
| `memoryThreshold` | `256KB` | 262.144 |

Một service có thể inject bean và đọc số byte:

~~~java
package com.example.service;

import com.example.config.StorageProperties;
import org.springframework.stereotype.Service;

@Service
public class StoragePolicy {
    private final long maxObjectBytes;
    private final long bufferBytes;

    public StoragePolicy(StorageProperties props) {
        this.maxObjectBytes = props.getMaxObjectSize().toBytes();
        this.bufferBytes = props.getUploadBuffer().toBytes();
    }

    public boolean accepts(long incomingBytes) {
        return incomingBytes >= 0 && incomingBytes <= maxObjectBytes;
    }

    public long getBufferBytes() {
        return bufferBytes;
    }
}
~~~

`DataSize` giúp code không phải tự tính `megabytes * 1024 * 1024` ở nhiều nơi. Tuy nhiên, việc chỉ kiểm tra `incomingBytes` ở lớp nghiệp vụ không thay thế giới hạn request/body mà server hoặc gateway cần áp dụng ở tầng HTTP.

## 7. Constructor binding: đặt `@DataSizeUnit` trên parameter

Với class bất biến, Spring Boot có thể bind properties qua constructor thay vì gọi setter. Khi đó annotation `@DataSizeUnit` được đặt tại **constructor parameter**:

~~~java
package com.example.config;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;
import org.springframework.boot.convert.DataSizeUnit;
import org.springframework.util.unit.DataSize;
import org.springframework.util.unit.DataUnit;

@ConfigurationProperties(prefix = "app.storage")
public final class StorageProperties {

    private final DataSize maxObjectSize;
    private final DataSize uploadBuffer;
    private final DataSize memoryThreshold;

    public StorageProperties(
            @DefaultValue("64MB") DataSize maxObjectSize,
            @DataSizeUnit(DataUnit.MEGABYTES)
            @DefaultValue("2MB") DataSize uploadBuffer,
            @DefaultValue("512B") DataSize memoryThreshold) {
        this.maxObjectSize = maxObjectSize;
        this.uploadBuffer = uploadBuffer;
        this.memoryThreshold = memoryThreshold;
    }

    public DataSize getMaxObjectSize() {
        return maxObjectSize;
    }

    public DataSize getUploadBuffer() {
        return uploadBuffer;
    }

    public DataSize getMemoryThreshold() {
        return memoryThreshold;
    }
}
~~~

Trong Spring Boot 3.x, một class cấu hình có một constructor nhận tham số thường có thể dùng constructor binding mà không cần thêm `@ConstructorBinding`.

Ý nghĩa từng annotation:

- `@DefaultValue("64MB")`: nếu thiếu `max-object-size`, binder dùng 64MB.
- `@DataSizeUnit(DataUnit.MEGABYTES)`: nếu `upload-buffer` được cung cấp là số trần như `8`, binder hiểu nó là 8MB.
- `@DefaultValue("2MB")`: nếu `upload-buffer` **bị thiếu hẳn**, binder có giá trị dự phòng 2MB.
- `@DefaultValue("512B")`: nếu `memory-threshold` thiếu, binder dùng 512 byte.

Lưu ý `@DefaultValue` là metadata của constructor binding, **không phải** API cho phép ghi property mặc định vào mọi `PropertySource`.

### 7.1. Đăng ký đúng cơ chế

Class constructor-bound cần được đăng ký bằng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties(StorageProperties.class)`. Không nên tạo nó qua một factory method `@Bean` thông thường rồi kỳ vọng Spring Boot tự cung cấp toàn bộ constructor arguments cho instance đó theo cơ chế constructor binding chuyên dụng.

Ví dụ đăng ký tường minh:

~~~java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(StorageProperties.class)
public class StorageConfiguration {
}
~~~

Nếu constructor có nhiều overload, có thể cần xác định constructor dùng để bind bằng `@ConstructorBinding` ở **constructor** thích hợp (theo API của Spring Boot 3.x), thay vì giả định mọi constructor đều dùng được.

## 8. Record `@ConfigurationProperties` với `DataSize`

Với Java 17+ và Spring Boot 3.x, record là một cách ngắn gọn để biểu diễn cấu hình bất biến ở cấp field:

~~~java
package com.example.config;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;
import org.springframework.boot.convert.DataSizeUnit;
import org.springframework.util.unit.DataSize;
import org.springframework.util.unit.DataUnit;

@ConfigurationProperties(prefix = "app.storage")
public record StorageProperties(
        @DefaultValue("64MB") DataSize maxObjectSize,
        @DataSizeUnit(DataUnit.MEGABYTES)
        @DefaultValue("2MB") DataSize uploadBuffer,
        @DefaultValue("512B") DataSize memoryThreshold) {
}
~~~

Đăng ký bằng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties(StorageProperties.class)`.

Cách truy cập của record:

~~~java
DataSize limit = props.maxObjectSize();
DataSize buffer = props.uploadBuffer();

long limitBytes = limit.toBytes();
long bufferBytes = buffer.toBytes();
~~~

Record accessor là `maxObjectSize()` và `uploadBuffer()` chứ không phải JavaBean getters `getMaxObjectSize()`/`getUploadBuffer()`.

Đặc biệt, `@DataSizeUnit(DataUnit.MEGABYTES)` ở record component cung cấp metadata cho constructor parameter tương ứng. Với YAML `upload-buffer: 8`, object nhận 8MB; với `upload-buffer: 512KB`, object nhận 512KB.

**Lưu ý về mặc định:** một record không có field initializer của instance như JavaBean; `@DefaultValue` là cách tường minh để cung cấp fallback cho constructor parameter. Nếu field bắt buộc không có cấu hình và không có default, nó có thể là `null`; nên thêm validation phù hợp.

## 9. `@DataSizeUnit` và `@DefaultValue` khác nhau

Đây là sự phân biệt cần nắm chắc:

| Công cụ | Áp dụng lúc nào? | Ví dụ |
| --- | --- | --- |
| `DataSize` | Chỉ ra kiểu dữ liệu Java | `private DataSize buffer;` |
| `@DataSizeUnit(MEGABYTES)` | Property có số nhưng **thiếu hậu tố** | `buffer: 8` → 8MB |
| `@DefaultValue("2MB")` | Property **không được cung cấp** trong constructor binding | Thiếu `buffer` → 2MB |
| Java field initializer | JavaBean được tạo và chưa bị override | `buffer = DataSize.ofMegabytes(2)` |
| `@NotNull` hoặc custom validation | Yêu cầu object hợp lệ sau binding | Thiếu/null không hợp lệ |

Ba kịch bản khác nhau cho một field record:

~~~java
@DataSizeUnit(DataUnit.MEGABYTES)
@DefaultValue("2MB")
DataSize uploadBuffer
~~~

1. Nguồn cấu hình có `upload-buffer: 8` → **8MB** nhờ đơn vị mặc định MB.
2. Nguồn cấu hình có `upload-buffer: 512KB` → **512KB** nhờ hậu tố tường minh.
3. Không có `upload-buffer` → **2MB** nhờ `@DefaultValue`.

Không nên nói “`@DataSizeUnit(MEGABYTES)` làm field có mặc định 1MB”. Annotation chỉ định đơn vị, không chỉ định số lượng và không thay đổi initializer mà bạn đã khai báo trong Java.

## 10. Khai báo trong `application.properties`, YAML và các nguồn khác

### 10.1. File Java Properties

~~~properties
app.storage.max-object-size=64MB
app.storage.upload-buffer=8
app.storage.memory-threshold=256KB
~~~

Các giá trị được chuyển đổi theo kiểu field, annotation và các converter của Spring Boot.

### 10.2. File YAML

~~~yaml
app:
  storage:
    max-object-size: "64MB"
    upload-buffer: 8
    memory-threshold: "256KB"
~~~

Có thể đặt chuỗi có hậu tố trong dấu nháy kép để dễ nhìn; số trần `8` vẫn được binder chuyển đổi theo `@DataSizeUnit`. Việc dùng dấu nháy YAML không tự định nghĩa đơn vị dung lượng.

### 10.3. Biến môi trường hệ điều hành

Với prefix `app.storage` và field `maxObjectSize`, biến môi trường chuẩn có dạng:

~~~bash
APP_STORAGE_MAXOBJECTSIZE=128MB
APP_STORAGE_UPLOADBUFFER=16
APP_STORAGE_MEMORYTHRESHOLD=512KB
~~~

Trong shell Unix, có thể chạy:

~~~bash
APP_STORAGE_MAXOBJECTSIZE=128MB APP_STORAGE_UPLOADBUFFER=16 java -jar app.jar
~~~

Nếu không có nguồn cấu hình nào ưu tiên hơn, `maxObjectSize` sẽ là 128MB và `uploadBuffer` sẽ là 16MB (giả sử field có `@DataSizeUnit(MEGABYTES)`).

Quy tắc tên environment variable trong Spring Boot configuration properties binding: thay dấu chấm bằng gạch dưới, **loại bỏ dấu gạch ngang**, chuyển sang chữ hoa. Ví dụ:

~~~text
app.storage.upload-buffer   → APP_STORAGE_UPLOADBUFFER
app.storage.max-object-size → APP_STORAGE_MAXOBJECTSIZE
~~~

Không nên mặc định rằng `APP_STORAGE_UPLOAD_BUFFER` là dạng tương đương chuẩn của mọi tên property; hãy dùng dạng canonical theo quy tắc trên và kiểm tra deployment thực tế.

### 10.4. Java system property và CLI

Cùng một cấu hình có thể được cung cấp qua `-D`:

~~~bash
java -Dapp.storage.upload-buffer=10MB -jar app.jar
~~~

Hoặc qua command-line option khi cơ chế này đang được cho phép:

~~~bash
java -jar app.jar --app.storage.upload-buffer=10MB
~~~

Hai hình thức trên là **hai property sources khác nhau**. `-D` thuộc JVM system properties, `--...` thuộc application command-line arguments. `@DataSizeUnit` chỉ quyết định cách diễn giải **giá trị số không hậu tố**, không thay đổi thứ tự ưu tiên của các nguồn.

## 11. Quy tắc precedence khi nhiều nguồn khai báo cùng dung lượng

Giả sử trong file:

~~~yaml
app:
  storage:
    max-object-size: 64MB
    upload-buffer: 8
~~~

Môi trường chạy cung cấp:

~~~bash
APP_STORAGE_UPLOADBUFFER=16
~~~

Và chương trình được khởi động:

~~~bash
APP_STORAGE_UPLOADBUFFER=16 java -jar app.jar --app.storage.upload-buffer=512KB
~~~

Trong cấu hình Spring Boot mặc định, nếu không có nguồn ưu tiên cao hơn:

- CLI cung cấp `512KB` và thường **ưu tiên hơn** OS environment.
- Biến môi trường cung cấp `16`, nhưng giá trị này không thắng trong lần chạy trên.
- YAML cung cấp `8`, có ưu tiên thấp hơn hai nguồn kể trên.

Kết quả `uploadBuffer` là **512KB**, không phải 16MB hay 8MB. Hậu tố `KB` tường minh làm annotation `@DataSizeUnit(MEGABYTES)` không thay đổi đơn vị của giá trị thắng.

Nếu bỏ CLI, biến môi trường `16` có thể thắng và được bind thành **16MB**. Nếu bỏ cả biến môi trường, YAML `8` có thể được bind thành **8MB**.

Bảng kết quả:

| Nguồn có mặt | Giá trị thắng | `uploadBuffer.toBytes()` |
| --- | --- | ---: |
| Chỉ YAML `8` | 8MB nhờ annotation | 8.388.608 |
| YAML `8` + env `16` | 16MB nhờ annotation | 16.777.216 |
| YAML `8` + env `16` + CLI `512KB` | 512KB | 524.288 |

Nếu `SpringApplication` đã gọi `setAddCommandLineProperties(false)` trước `run`, nguồn command-line properties thông thường không được thêm vào `Environment`; kết quả khi đó phụ thuộc các nguồn còn lại.

`@DataSizeUnit` không tạo ưu tiên riêng, cũng không gộp nhiều số dung lượng lại. Quy tắc priority và conversion là hai bước khác nhau.

## 12. Dùng `DataSize` trong logic nghiệp vụ

`DataSize` hữu ích vì code có thể làm việc bằng kiểu có ý nghĩa thay vì chuỗi chưa parse.

Ví dụ:

~~~java
import org.springframework.util.unit.DataSize;

public final class UploadGuard {
    private final DataSize maxSize;

    public UploadGuard(DataSize maxSize) {
        this.maxSize = maxSize;
    }

    public boolean allows(long incomingSizeBytes) {
        return incomingSizeBytes >= 0
                && incomingSizeBytes <= maxSize.toBytes();
    }
}
~~~

Sử dụng:

~~~java
UploadGuard guard =
        new UploadGuard(DataSize.ofMegabytes(64));

boolean accepted = guard.allows(5L * 1024 * 1024);
~~~

Một ứng dụng Spring Boot có thể tạo bean từ properties:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class UploadConfiguration {

    @Bean
    UploadGuard uploadGuard(StorageProperties properties) {
        return new UploadGuard(properties.getMaxObjectSize());
    }
}
~~~

Ví dụ `getMaxObjectSize()` dùng với JavaBean ở mục 6. Nếu bạn chọn record, thay bằng `properties.maxObjectSize()`.

**Phân biệt:** logic `UploadGuard` chỉ là một kiểm tra của ứng dụng; nó không tự động giới hạn lượng byte được reverse proxy, web server hoặc multipart resolver nhận vào trước khi code này được chạy.

### 12.1. So sánh `DataSize` không cần chuyển sang một đơn vị gần đúng

Có thể so sánh trực tiếp:

~~~java
DataSize current = DataSize.ofKilobytes(1536);
DataSize limit = DataSize.ofMegabytes(2);

if (current.compareTo(limit) <= 0) {
    // Current = 1.5MB, nhỏ hơn limit 2MB.
}
~~~

Hoặc dùng `toBytes()` để so sánh chính xác. Không nên chuyển mọi giá trị về `toMegabytes()` rồi so sánh khi cần độ chính xác đến byte, vì cách chuyển về đơn vị lớn có thể làm mất phần dư. Chẳng hạn, `DataSize.ofKilobytes(1536).toMegabytes()` trả về số nguyên **1**, trong khi dung lượng thực là 1,5MB.

## 13. Kết hợp với Bean Validation

Binding thành công **không đảm bảo dung lượng phù hợp nghiệp vụ**. Ví dụ, `0B` hoặc `-5MB` vẫn là các giá trị biểu diễn được bằng `DataSize`, nhưng một buffer âm hoặc một giới hạn upload bằng 0 có thể không hợp lệ.

Trước hết có thể kiểm tra field không null:

~~~java
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;
import org.springframework.util.unit.DataSize;

@Validated
@ConfigurationProperties(prefix = "app.storage")
public class StorageProperties {
    @NotNull
    private DataSize maxObjectSize;

    // getter và setter
}
~~~

Trong Spring Boot 3.x, cần một Bean Validation implementation phù hợp, thường qua `spring-boot-starter-validation`. `@NotNull` không tự kiểm tra `maxObjectSize.toBytes() > 0`; nếu cần yêu cầu dung lượng phải dương, có thể dùng validator chuyên biệt hoặc kiểm tra tường minh khi khởi tạo dependency.

Ví dụ:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.util.unit.DataSize;

@Configuration(proxyBeanMethods = false)
public class StoragePolicyConfiguration {

    @Bean
    StoragePolicy storagePolicy(StorageProperties properties) {
        DataSize max = properties.getMaxObjectSize();
        DataSize buffer = properties.getUploadBuffer();

        if (max == null || max.toBytes() <= 0) {
            throw new IllegalStateException(
                    "app.storage.max-object-size must be positive");
        }
        if (buffer == null || buffer.toBytes() <= 0) {
            throw new IllegalStateException(
                    "app.storage.upload-buffer must be positive");
        }
        if (buffer.compareTo(max) > 0) {
            throw new IllegalStateException(
                    "app.storage.upload-buffer must not exceed max-object-size");
        }

        return new StoragePolicy(max, buffer);
    }
}
~~~

Ở đây `StoragePolicy` là class nghiệp vụ minh họa nhận hai `DataSize`. Việc tạo bean này cần một implementation tương ứng; phần quan trọng là **ràng buộc được kiểm tra sau khi config đã bind**.

Trong một hệ thống production, có thể áp dụng Jakarta custom constraint để kiểm tra chéo các trường hoặc dùng constructor validation với thông báo lỗi rõ ràng. Đừng dùng `@Min(1)` trực tiếp lên `DataSize` và mặc định Bean Validation sẽ tự hiểu đó là đơn vị byte; `@Min` được thiết kế cho các kiểu số được hỗ trợ, còn `DataSize` là value type riêng.

### 13.1. Không dùng size âm làm cơ chế “unlimited” nếu không có contract

Một số API thư viện hoặc server chấp nhận `-1` để biểu thị không giới hạn, nhưng **đó là quy ước của API cụ thể**, không phải ý nghĩa chung của `DataSize.ofBytes(-1)`. Đừng quy định chung “âm nghĩa là unlimited” cho mọi thuộc tính `DataSize`.

Nếu cấu hình nghiệp vụ cần “không giới hạn”, hãy định nghĩa rõ bằng boolean/enum hoặc ghi nhận semantics đặc thù của thành phần nhận giá trị.

## 14. Ví dụ thực tế với giới hạn multipart upload

Spring Boot có các thuộc tính multipart để điều chỉnh upload file, chẳng hạn:

~~~properties
spring.servlet.multipart.max-file-size=10MB
spring.servlet.multipart.max-request-size=20MB
~~~

Trong ứng dụng Spring MVC có cấu hình multipart được hỗ trợ, các giá trị này điều khiển giới hạn upload mà Spring Boot cung cấp cho multipart handling.

Phân biệt hai cấp độ:

- `max-file-size`: giới hạn một file trong multipart request.
- `max-request-size`: giới hạn tổng kích thước của multipart request.

Một HTTP request có thể chứa nhiều file và các trường form, nên `max-request-size` có ý nghĩa khác `max-file-size`.

Nếu ứng dụng có chính sách riêng `app.storage.max-object-size=64MB`, thuộc tính custom đó **không tự động** thay thế `spring.servlet.multipart.max-file-size`. Phải cấu hình đúng thuộc tính hạ tầng và chỉ định logic nghiệp vụ tương ứng.

Ví dụ:

~~~yaml
spring:
  servlet:
    multipart:
      max-file-size: 10MB
      max-request-size: 12MB

app:
  storage:
    max-object-size: 8MB
    upload-buffer: 2MB
~~~

Trong ví dụ này, chính sách nghiệp vụ đặt giới hạn object 8MB, còn tầng multipart cho phép file tối đa 10MB. Cần xác định rõ yêu cầu và bảo đảm client nhận thông báo lỗi phù hợp khi vượt giới hạn.

Nếu có reverse proxy, ingress controller hoặc API gateway đứng trước ứng dụng, các giới hạn kích thước request ở tầng đó cũng có thể được áp dụng độc lập.

## 15. Tránh nhầm `DataSize` với `Duration`

Spring Boot hỗ trợ nhiều kiểu conversion cho cấu hình có đơn vị. Hai kiểu dễ bị nhầm:

| Đặc điểm | `DataSize` | `Duration` |
| --- | --- | --- |
| Đại lượng | Dung lượng dữ liệu | Khoảng thời gian |
| Package | `org.springframework.util.unit.DataSize` | `java.time.Duration` |
| Annotation đơn vị mặc định | `@DataSizeUnit` | `@DurationUnit` |
| Đơn vị ví dụ | `B`, `KB`, `MB`, `GB`, `TB` | `ns`, `us`, `ms`, `s`, `m`, `h`, `d` |
| Không có hậu tố | Mặc định byte | Mặc định milli giây |
| Giá trị dễ đọc | `16MB` | `10s` |

Ví dụ một config class có cả hai:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.convert.DataSizeUnit;
import org.springframework.boot.convert.DurationUnit;
import org.springframework.util.unit.DataSize;
import org.springframework.util.unit.DataUnit;
import java.time.temporal.ChronoUnit;

@ConfigurationProperties(prefix = "app.transfer")
public class TransferProperties {
    @DataSizeUnit(DataUnit.MEGABYTES)
    private DataSize bufferSize = DataSize.ofMegabytes(4);

    @DurationUnit(ChronoUnit.SECONDS)
    private Duration timeout = Duration.ofSeconds(15);

    // getters và setters
}
~~~

YAML:

~~~yaml
app:
  transfer:
    buffer-size: 8
    timeout: 30
~~~

`buffer-size: 8` được hiểu là 8MB; `timeout: 30` được hiểu là 30 giây. Dù cả hai là số không hậu tố, annotation quy định **hai loại đơn vị khác nhau**.

Nếu viết rõ `buffer-size: 512KB` và `timeout: 500ms` thì các hậu tố tường minh được dùng.

## 16. Đọc và phân tích `DataSize` trong mã Java

Ngoài Spring Boot binding, Spring Framework cho phép parse một dung lượng trong Java:

~~~java
import org.springframework.util.unit.DataSize;
import org.springframework.util.unit.DataUnit;

DataSize a = DataSize.parse("12KB");
DataSize b = DataSize.parse("5MB");
DataSize c = DataSize.parse("20");
DataSize d = DataSize.parse("20", DataUnit.KILOBYTES);

System.out.println(a.toBytes()); // 12288
System.out.println(b.toBytes()); // 5242880
System.out.println(c.toBytes()); // 20
System.out.println(d.toBytes()); // 20480
~~~

Các factory method tạo giá trị không cần parse chuỗi:

~~~java
DataSize byteSize = DataSize.ofBytes(512);
DataSize kiloSize = DataSize.ofKilobytes(256);
DataSize megaSize = DataSize.ofMegabytes(8);
DataSize custom = DataSize.of(3, DataUnit.GIGABYTES);
~~~

Các method hữu ích:

| Method | Ý nghĩa |
| --- | --- |
| `toBytes()` | Trả về số byte dạng `long` |
| `toKilobytes()` | Quy đổi sang KB dạng số nguyên |
| `toMegabytes()` | Quy đổi sang MB dạng số nguyên |
| `toGigabytes()` | Quy đổi sang GB dạng số nguyên |
| `compareTo(other)` | So sánh hai kích thước |
| `isNegative()` | Kiểm tra dung lượng âm |

`DataSize` biểu diễn lượng byte bằng `long`. Khi vận hành với số cực lớn, cân nhắc giới hạn biểu diễn và overflow trước khi tính toán cộng/nhân dung lượng ngoài phạm vi an toàn.

Không nên tự viết parser dung lượng đơn giản kiểu “bỏ hai ký tự cuối rồi nhân 1.000” khi đã có `DataSize` và Spring Boot binder; cách tự viết dễ sai cả suffix, phân biệt byte/binary unit và giới hạn số.

## 17. Kiểm thử binding bằng `ApplicationContextRunner`

Khi một cấu hình có cả suffix lẫn `@DataSizeUnit`, nên có unit/integration test cho những input quan trọng.

Ví dụ tối giản với một record chuyên dùng trong test:

~~~java
package com.example.config;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.convert.DataSizeUnit;
import org.springframework.util.unit.DataSize;
import org.springframework.util.unit.DataUnit;

@ConfigurationProperties(prefix = "app.storage")
public record StorageProperties(
        @DataSizeUnit(DataUnit.MEGABYTES) DataSize uploadBuffer,
        DataSize memoryThreshold) {
}
~~~

Kiểm tra trong một test có `spring-boot-starter-test`:

~~~java
package com.example.config;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.context.ConfigurationPropertiesAutoConfiguration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class StoragePropertiesBindingTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                .withConfiguration(AutoConfigurations.of(
                    ConfigurationPropertiesAutoConfiguration.class))
                .withUserConfiguration(TestConfiguration.class);

    @Test
    void interpretsDefaultUnitAndExplicitSuffix() {
        runner
            .withPropertyValues(
                "app.storage.upload-buffer=8",
                "app.storage.memory-threshold=256KB")
            .run(context -> {
                assertThat(context).hasNotFailed();
                StorageProperties props =
                        context.getBean(StorageProperties.class);

                assertThat(props.uploadBuffer().toBytes())
                        .isEqualTo(8L * 1024 * 1024);
                assertThat(props.memoryThreshold().toBytes())
                        .isEqualTo(256L * 1024);
            });
    }

    @Test
    void explicitUnitOverridesDefaultUnit() {
        runner
            .withPropertyValues(
                "app.storage.upload-buffer=512KB",
                "app.storage.memory-threshold=10")
            .run(context -> {
                StorageProperties props =
                        context.getBean(StorageProperties.class);

                assertThat(props.uploadBuffer().toBytes())
                        .isEqualTo(512L * 1024);
                assertThat(props.memoryThreshold().toBytes())
                        .isEqualTo(10);
            });
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(StorageProperties.class)
    static class TestConfiguration {
    }
}
~~~

Kiểu cấu hình test ở đây dùng annotation trên record để bảo đảm hai property được bind vào `DataSize`. `ApplicationContextRunner` cho phép chạy context nhỏ với các property values cụ thể, dễ phân biệt số không hậu tố, suffix tường minh và input sai định dạng.

Đối với một module có quy tắc bắt buộc, nên thêm test **thiếu property**, **giá trị âm**, **giá trị bằng 0**, **quá ngưỡng** và **override từ nguồn ưu tiên cao**. Những case này thuộc trách nhiệm nghiệp vụ riêng, không phải tất cả đều do converter `DataSize` tự kiểm tra.

## 18. Chẩn đoán lỗi khi chuyển đổi dung lượng thất bại

Những biểu hiện thường gặp:

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `buffer-size: 8` thành 8 byte, không phải 8MB | Field không có `@DataSizeUnit` | Ghi rõ `8MB` hoặc đặt annotation trên field/parameter đúng chỗ |
| `@DataSizeUnit` có nhưng thiếu config vẫn là `null` | Annotation chỉ đặt unit, không đặt default | Dùng field initializer hoặc `@DefaultValue` cho constructor binding |
| `buffer-size: 512KB` không thành 512MB | Hậu tố `KB` là đơn vị tường minh | Hiểu đúng: explicit suffix thắng default unit |
| `memory-threshold: 1.5MB` gây conversion error | Định dạng có dấu thập phân không thuộc dạng số nguyên chuẩn | Viết `1536KB` |
| `max-object-size: 64 MB` gặp lỗi | Khoảng trắng giữa số và suffix không thuộc dạng chuẩn | Dùng `64MB` |
| Giá trị sai kiểu làm app không start | Không chuyển được từ string sang `DataSize` | Sửa key/value, kiểm tra thông báo binding |
| Con số quá lớn | Vượt giới hạn số byte biểu diễn bằng `long` | Đặt giới hạn và chọn kích thước hợp lý |
| Hành vi khác giữa profile dev/prod | Property source có mức ưu tiên khác nhau | Kiểm tra các file profile và nguồn ghi đè |
| Biến môi trường không có tác dụng | Tên env var không khớp relaxed binding canonical | Dùng `APP_STORAGE_UPLOADBUFFER` đúng quy tắc |
| Dung lượng đã bind đúng nhưng request vẫn bị từ chối | Web server, proxy hoặc multipart có giới hạn riêng | Kiểm tra cả tầng HTTP và business policy |

### 18.1. Quan sát giá trị hiệu lực

Trong môi trường phát triển, có thể inject bean cấu hình rồi quan sát số byte:

~~~java
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class StorageDebugConfiguration {

    @Bean
    ApplicationRunner printStorageLimits(StorageProperties props) {
        return args -> {
            System.out.println("maxObjectBytes="
                    + props.getMaxObjectSize().toBytes());
            System.out.println("uploadBufferBytes="
                    + props.getUploadBuffer().toBytes());
        };
    }
}
~~~

Đoạn code này giả định đang dùng JavaBean `StorageProperties` ở phần 6. Nếu dùng record, chuyển sang record accessors. Ví dụ không chứa secret; trong ứng dụng thực tế tránh log những giá trị nhạy cảm hoặc thông tin hạ tầng không cần thiết.

Spring Boot Actuator có thể cung cấp `/actuator/env` và `/actuator/configprops` khi được bật, giúp xác định nguồn property và giá trị đã bind. Chỉ bật và cấp quyền theo chính sách bảo mật; không mở công khai các endpoint có thể lộ thông tin cấu hình.

## 19. Những nhầm lẫn thường gặp

| Nhầm lẫn | Hiểu đúng |
| --- | --- |
| “`DataSize` chỉ là `long` có tên mới.” | Nó là một value type thể hiện dung lượng, hỗ trợ factory, parse, conversion và so sánh. |
| “Số `10` tự hiểu là 10MB.” | Không có annotation, đơn vị mặc định của `DataSize` là byte. |
| “`@DataSizeUnit(MEGABYTES)` làm mọi input thành MB.” | Chỉ đặt đơn vị khi input không có hậu tố; `256KB` vẫn là KB. |
| “Annotation này đặt mặc định 1MB khi thiếu property.” | Không. Dùng initializer hoặc `@DefaultValue` cho giá trị fallback. |
| “`1MB` luôn bằng 1.000.000 byte.” | Trong `DataUnit` của Spring, `1MB` bằng 1.048.576 byte. |
| “`toMegabytes()` luôn là phép chia chính xác có phần thập phân.” | Nó trả số nguyên; dùng `toBytes()` hoặc compareTo khi cần chính xác đến byte. |
| “`-1B` luôn nghĩa là unlimited.” | Ý nghĩa âm tùy API sử dụng; `DataSize` không tự định nghĩa unlimited chung. |
| “`@Min(1)` trên `DataSize` tự kiểm tra dương.” | Cần constraint phù hợp với kiểu hoặc custom validation dùng `toBytes()`. |
| “Thiết lập `app.storage.max-object-size` sẽ tự chặn multipart upload.” | Property custom chỉ có hiệu lực nếu ứng dụng sử dụng nó; tầng HTTP có các property riêng. |
| “Dùng record nghĩa là không thể đặt `@DataSizeUnit`.” | Annotation có thể đặt tại component/constructor parameter cho binding tương ứng. |
| “`@DataSizeUnit` thay đổi thứ tự ưu tiên property sources.” | Không, nó chỉ ảnh hưởng đơn vị khi conversion. |

## 20. Bài tập thực hành

### 20.1. Đề bài

Cho record:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;
import org.springframework.boot.convert.DataSizeUnit;
import org.springframework.util.unit.DataSize;
import org.springframework.util.unit.DataUnit;

@ConfigurationProperties(prefix = "app.cache")
public record CacheProperties(
        @DataSizeUnit(DataUnit.MEGABYTES)
        @DefaultValue("4MB") DataSize entryLimit,
        @DefaultValue("512KB") DataSize writeBuffer,
        DataSize minimumFreeSpace) {
}
~~~

File `application.yml`:

~~~yaml
app:
  cache:
    entry-limit: 10
    write-buffer: 2MB
    minimum-free-space: 1GB
~~~

**Câu 1:** `entryLimit` bằng bao nhiêu byte?

**Đáp án:** 10MB = **10.485.760 byte**, do `@DataSizeUnit(MEGABYTES)` diễn giải số trần `10`.

**Câu 2:** `writeBuffer` bằng bao nhiêu byte?

**Đáp án:** 2MB = **2.097.152 byte**, bởi suffix `MB` được ghi rõ.

**Câu 3:** `minimumFreeSpace` bằng bao nhiêu byte?

**Đáp án:** 1GB = **1.073.741.824 byte**, vì suffix `GB` được cung cấp.

**Câu 4:** Nếu xóa `entry-limit` khỏi YAML nhưng vẫn giữ record thì sao?

**Đáp án:** giá trị mặc định là 4MB theo `@DefaultValue("4MB")`; `@DataSizeUnit` không phải nguồn tạo default.

**Câu 5:** Nếu đổi `entry-limit: 10` thành `entry-limit: 512KB` thì sao?

**Đáp án:** giá trị là 512KB = **524.288 byte**. Annotation MB không ghi đè đơn vị có suffix rõ ràng.

**Câu 6:** Nếu thêm biến môi trường `APP_CACHE_ENTRYLIMIT=20MB` và CLI `--app.cache.entry-limit=8MB` trong chế độ command-line properties được bật, kết quả là gì?

**Đáp án:** với các nguồn thông thường và không có nguồn ưu tiên cao hơn, CLI thắng nên `entryLimit=8MB`. Không cộng 8MB với 20MB hay với 10MB trong YAML.

### 20.2. Bài tập áp dụng

Hãy tạo một `@ConfigurationProperties(prefix = "app.archive")` class chứa:

- `segmentSize`: mặc định 8MB, nhưng cho phép ghi `segment-size: 16` như 16MB.
- `maxArchiveSize`: bắt buộc, phải ghi rõ ví dụ `2GB`.
- `minFreeSpace`: mặc định 512KB.

Sau đó viết một validator bảo đảm:

~~~text
segmentSize > 0
maxArchiveSize > 0
minFreeSpace >= 0
segmentSize <= maxArchiveSize
~~~

Gợi ý: dùng `DataSize.of...(...)`, `@DataSizeUnit(DataUnit.MEGABYTES)`, `@DefaultValue` nếu dùng constructor binding, `toBytes()` hoặc `compareTo(...)` khi so sánh, và kiểm tra null trước khi đọc.

## 21. Ghi nhớ

1. **`DataSize`** là kiểu giá trị dung lượng trong Spring Framework, biểu diễn chính xác số byte và hỗ trợ chuyển đổi từ hậu tố `B`, `KB`, `MB`, `GB`, `TB`.
2. **Mặc định số không hậu tố là byte.** Vì vậy `8` khác hoàn toàn `8MB`.
3. **`@DataSizeUnit`** thay đơn vị mặc định khi binding một giá trị không có hậu tố, ví dụ `@DataSizeUnit(MEGABYTES)` biến `8` thành 8MB.
4. **Hậu tố tường minh được ưu tiên:** `512KB` luôn là 512KB, dù annotation quy định default là MB.
5. **`@DataSizeUnit` không cấp giá trị fallback khi property vắng mặt.** Dùng JavaBean initializer hoặc `@DefaultValue` cho constructor/record binding.
6. **Dung lượng trong `DataUnit` theo lũy thừa của 2:** `1KB=1.024B` và `1MB=1.048.576B`.
7. **Validation là trách nhiệm riêng:** kiểu `DataSize` không tự bảo đảm giá trị dương, phù hợp ngân sách RAM, đúng ngưỡng upload hoặc chính sách hạ tầng.
8. **Phân biệt `DataSize` và `Duration`:** một kiểu biểu diễn dung lượng, một kiểu biểu diễn thời gian; annotation đơn vị mặc định cũng khác nhau.
9. **Tất cả nguồn config data vẫn tuân theo thứ tự ưu tiên của `Environment`:** conversion sang `DataSize` diễn ra sau khi nguồn và giá trị hiệu lực đã được xác định.

### Tài liệu tham khảo

- Spring Boot Reference — Externalized Configuration, Converting Data Sizes: https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.conversion.data-sizes
- Spring Boot 3.3 Reference — Externalized Configuration: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Framework Javadoc — DataSize: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/util/unit/DataSize.html
- Spring Framework Javadoc — DataUnit: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/util/unit/DataUnit.html
- Spring Boot Reference — Properties Validation: https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.validation
