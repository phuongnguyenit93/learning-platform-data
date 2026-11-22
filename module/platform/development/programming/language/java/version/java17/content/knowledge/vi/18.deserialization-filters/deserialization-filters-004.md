# Giới hạn lớp, độ sâu, số tham chiếu, số byte và kích thước mảng khi lọc giải tuần tự hóa

Java serialization có thể tái tạo một đồ thị object từ dữ liệu nhị phân. Khi đọc một stream, `ObjectInputStream` có thể tạo nhiều object, liên kết chúng với nhau, xử lý mảng và khôi phục các tham chiếu lặp hoặc vòng tham chiếu. Nếu dữ liệu đến từ nguồn không đáng tin cậy, đồ thị quá lớn hoặc chứa những lớp ngoài dự kiến có thể gây tiêu thụ bộ nhớ, CPU hoặc kích hoạt hành vi không mong muốn trong quá trình deserialization.

Từ Java 9, Java cung cấp **serialization filtering** qua `java.io.ObjectInputFilter` (JEP 290). Java 17 tiếp tục hỗ trợ API này. Filter cho phép giới hạn:

- **Lớp được phép giải tuần tự hóa** (*class filtering*).
- **Độ sâu đồ thị object** (*maximum depth*).
- **Số tham chiếu** (*maximum references*).
- **Số byte đã đọc từ stream** (*maximum stream bytes*).
- **Kích thước mảng** (*maximum array length*).

Các giới hạn này thường được kết hợp. Ví dụ, một request có thể chỉ được đọc các DTO thuộc package được cho phép, đồ thị không sâu hơn 20 cấp, không vượt 1.000 tham chiếu, không tiêu thụ quá 1 MiB dữ liệu và không tạo mảng dài hơn 10.000 phần tử.

`ObjectInputFilter` là cơ chế kiểm soát dữ liệu **đang được giải tuần tự hóa**. Nó không thay thế xác thực nghiệp vụ, kiểm tra kích thước ở tầng mạng, hoặc việc chọn định dạng dữ liệu an toàn hơn khi không cần Java native serialization.

## 1. Vì sao cần lọc khi giải tuần tự hóa?

Với Java serialization, dữ liệu không chỉ là một dãy field đơn giản. Một object có thể tham chiếu đến object khác; các object có thể chia sẻ tham chiếu hoặc tạo vòng lặp:

```text
Request
  ├── User
  │    ├── Profile
  │    └── Preferences
  ├── Orders[]
  │    ├── Order
  │    └── Order
  └── Metadata
```

Khi khôi phục đồ thị này, JVM phải đọc class descriptor, cấp phát object và mảng, rồi nối các tham chiếu. Nếu đầu vào không bị giới hạn, một stream có thể:

- Yêu cầu khôi phục lớp mà ứng dụng không dự định nhận.
- Tạo đồ thị lồng nhau rất sâu.
- Chứa số lượng tham chiếu rất lớn.
- Tiêu thụ lượng dữ liệu stream vượt quá ngân sách.
- Yêu cầu mảng có kích thước rất lớn.

Filter cho phép ứng dụng từ chối đồ thị ngay trong quá trình đọc, trước khi tiếp tục khôi phục các object bị chặn.

### 1.1. Filter không tự động được bật cho mọi ứng dụng

Không nên giả định Java 17 tự áp một allowlist hoặc các ngưỡng phù hợp cho mọi `ObjectInputStream`. Ứng dụng cần chủ động cấu hình filter theo dữ liệu và lớp thực sự được phép nhận.

Nếu hệ thống vẫn dùng Java serialization, hãy cấu hình filter trước khi đọc object đầu tiên. Với dữ liệu không tin cậy, cần kết hợp allowlist lớp với các giới hạn tài nguyên; chỉ đặt một ngưỡng kích thước mà không giới hạn lớp vẫn có thể cho phép những kiểu object không mong muốn.

## 2. ObjectInputFilter và FilterInfo

API chính:

```java
import java.io.ObjectInputFilter;
```

`ObjectInputFilter` là một functional interface. Filter nhận `ObjectInputFilter.FilterInfo` mô tả trạng thái đang được giải tuần tự hóa và trả về một trong ba trạng thái:

| Trạng thái | Ý nghĩa |
| --- | --- |
| `ALLOWED` | Filter cho phép đối tượng hoặc trạng thái đang xét. |
| `REJECTED` | Từ chối; quá trình deserialization bị hủy và thường phát sinh `InvalidClassException`. |
| `UNDECIDED` | Filter chưa quyết định; kết quả còn phụ thuộc các filter khác hoặc cơ chế xử lý mặc định. |

`FilterInfo` cung cấp các thông tin quan trọng:

| Phương thức | Thông tin |
| --- | --- |
| `serialClass()` | Lớp đang được xem xét; có thể là `null` khi thông tin không gắn với một lớp mới cụ thể. |
| `arrayLength()` | Độ dài mảng đang được giải tuần tự hóa; giá trị âm nếu không phải mảng. |
| `depth()` | Độ sâu hiện tại của đồ thị object. |
| `references()` | Số tham chiếu đã được xử lý trong stream. |
| `streamBytes()` | Số byte đã được đọc từ stream tại thời điểm filter được gọi. |

Một filter có thể dựa vào các giá trị này để quyết định chấp nhận hay từ chối dữ liệu.

### 2.1. Hai nhóm điều kiện

Thông thường, nên chia điều kiện thành hai nhóm:

1. **Giới hạn tài nguyên:** `depth`, `references`, `streamBytes`, `arrayLength`.
2. **Giới hạn kiểu:** `serialClass`.

Nếu bất kỳ ngưỡng tài nguyên nào bị vượt, từ chối ngay. Nếu chưa vượt, kiểm tra lớp có thuộc tập cho phép hay không.

## 3. Bốn giới hạn tài nguyên

Java serialization filter hỗ trợ bốn ngưỡng độc lập. Chúng kiểm soát các khía cạnh khác nhau của đồ thị và stream.

### 3.1. maxdepth: giới hạn độ sâu đồ thị

`maxdepth` giới hạn số cấp lồng nhau của đồ thị object đang được giải tuần tự hóa.

Ví dụ:

```text
maxdepth=20
```

Nếu đồ thị có cấu trúc:

```text
Order
  └── Customer
       └── Address
            └── Country
```

thì mỗi bước lồng object làm tăng độ sâu theo quá trình đọc. Một đồ thị có chuỗi tham chiếu lồng nhau quá sâu có thể làm tăng chi phí xử lý hoặc gây áp lực lên stack.

`maxdepth` phù hợp để giới hạn cấu trúc lồng nhau bất thường. Nó **không** giới hạn tổng số object trong đồ thị: một node có thể tham chiếu hàng nghìn node con ở cùng một mức. Vì vậy cần kết hợp với `maxrefs`.

### 3.2. maxrefs: giới hạn số tham chiếu

`maxrefs` giới hạn số tham chiếu được ghi nhận trong stream. Đây là giới hạn hữu ích khi đồ thị có rất nhiều object hoặc liên kết:

```text
maxrefs=1000
```

Một đồ thị có thể nông nhưng rất rộng:

```text
Catalog
  ├── Item 1
  ├── Item 2
  ├── Item 3
  ├── ...
  └── Item 50000
```

Trong ví dụ, độ sâu có thể nhỏ nhưng số tham chiếu rất lớn. `maxdepth` đơn lẻ không kiểm soát được trường hợp này; `maxrefs` bổ sung giới hạn theo số lượng.

Tham chiếu lặp và back-reference cũng là một phần của cơ chế serialization. Không nên tự suy ra số object nghiệp vụ từ `references()`; hãy dùng nó như bộ đếm tài nguyên theo hợp đồng của filter.

### 3.3. maxbytes: giới hạn byte đọc từ stream

`maxbytes` giới hạn số byte được tiêu thụ từ input stream:

```text
maxbytes=1048576
```

Giá trị trên tương ứng 1 MiB. Đây là ngân sách tổng thể cho dữ liệu serialized đã đọc, hữu ích khi một payload có thể chứa nhiều object hoặc field.

`maxbytes` khác với kích thước file ở tầng lưu trữ:

- Filter quan sát số byte đã đọc từ serialization stream.
- Lớp HTTP, message broker hoặc file upload có thể cần giới hạn riêng trước khi tạo `ObjectInputStream`.
- Một stream có thể có framing hoặc dữ liệu bao quanh ngoài phần serialization; ngân sách ở tầng transport vẫn cần được áp dụng độc lập.

Không nên dựa duy nhất vào `maxbytes` để bảo vệ toàn bộ pipeline nhận dữ liệu. Hãy giới hạn payload ở tầng đầu vào và dùng filter như lớp bảo vệ bổ sung bên trong deserialization.

### 3.4. maxarray: giới hạn chiều dài mảng

`maxarray` giới hạn số phần tử của một mảng được khôi phục:

```text
maxarray=10000
```

Ví dụ dữ liệu có thể chứa:

```java
byte[] payload;
String[] labels;
Order[] orders;
```

Nếu stream yêu cầu mảng dài vượt quá ngưỡng, filter có thể từ chối trước khi mảng được tạo theo yêu cầu đó.

`maxarray` là số phần tử, không phải số byte. Ví dụ:

- `byte[10000]` có 10.000 phần tử byte.
- `int[10000]` cũng có 10.000 phần tử nhưng phần dữ liệu phần tử có kích thước lớn hơn.
- `String[10000]` có 10.000 slot tham chiếu; các chuỗi bên trong còn là object riêng.

Giới hạn mảng không thay thế `maxbytes` hoặc `maxrefs`. Mảng có kích thước vừa phải vẫn có thể chứa nhiều object; một stream không có mảng lớn vẫn có thể tiêu thụ nhiều byte.

## 4. Kết hợp bốn ngưỡng

Một cấu hình thường cần giới hạn đồng thời cả bốn chiều:

```text
maxdepth=20;maxrefs=1000;maxbytes=1048576;maxarray=10000
```

Ý nghĩa:

| Giới hạn | Giá trị ví dụ | Mục tiêu |
| --- | ---: | --- |
| `maxdepth` | 20 | Không cho đồ thị lồng sâu hơn mức cho phép. |
| `maxrefs` | 1.000 | Hạn chế tổng số tham chiếu được xử lý. |
| `maxbytes` | 1.048.576 | Hạn chế byte đã đọc từ stream ở mức 1 MiB. |
| `maxarray` | 10.000 | Hạn chế chiều dài của mỗi mảng. |

Đây chỉ là **giá trị minh họa**, không phải ngưỡng phù hợp cho mọi ứng dụng. Hãy đo payload hợp lệ thực tế, xác định kích thước tối đa theo nghiệp vụ và để một khoảng dự phòng hợp lý. Ngưỡng quá thấp làm hỏng request hợp lệ; ngưỡng quá cao làm giảm tác dụng bảo vệ.

### 4.1. Vì sao không chỉ đặt maxbytes?

Giả sử một payload nhỏ nhưng mô tả nhiều object nhỏ. Tổng byte có thể chưa lớn nhưng số tham chiếu cao. Ngược lại, một object có mảng lớn có thể tiêu thụ nhiều bộ nhớ dù độ sâu và số node không cao.

Các ngưỡng bổ sung nhau:

- `maxdepth`: giới hạn cấu trúc lồng nhau.
- `maxrefs`: giới hạn độ rộng/số liên kết được xử lý.
- `maxbytes`: giới hạn lượng dữ liệu serialized đã đọc.
- `maxarray`: giới hạn kích thước từng mảng.

## 5. Giới hạn lớp: allowlist và denylist

Giới hạn tài nguyên không trả lời câu hỏi **lớp nào được phép xuất hiện**. `serialClass()` cho phép filter kiểm tra kiểu object đang được khôi phục.

Một chiến lược thường dễ kiểm soát là **allowlist**:

- Cho phép các DTO cụ thể hoặc package DTO đã xác định.
- Cho phép các kiểu nền tảng thật sự cần cho cấu trúc dữ liệu.
- Từ chối các lớp còn lại.

Ví dụ giả định ứng dụng chỉ nhận các kiểu trong package `com.example.dto`:

```text
com.example.dto.**
```

Một filter theo pattern có thể kết hợp giới hạn và class pattern:

```java
String pattern =
        "maxdepth=20;" +
        "maxrefs=1000;" +
        "maxbytes=1048576;" +
        "maxarray=10000;" +
        "com.example.dto.**;" +
        "java.lang.String;" +
        "!*";

ObjectInputFilter filter =
        ObjectInputFilter.Config.createFilter(pattern);
```

Trong pattern:

- `com.example.dto.**` khớp các lớp trong package đó và các package con.
- `java.lang.String` cho phép kiểu chuỗi nếu nó xuất hiện trong đồ thị được lọc.
- `!*` từ chối mọi lớp không khớp những pattern cho phép đứng trước.

Các pattern được phân tách bằng dấu chấm phẩy và được xét theo thứ tự. Những giới hạn `max...` được kiểm tra như các ngưỡng tài nguyên; nếu vượt giới hạn, filter từ chối. Với phần class pattern, thứ tự cho phép đặt các quy tắc cụ thể trước quy tắc từ chối tổng quát ở cuối.

### 5.1. *, package.* và package.**

Các pattern lớp phổ biến:

| Pattern | Ý nghĩa |
| --- | --- |
| `com.example.dto.Customer` | Một lớp cụ thể. |
| `com.example.dto.*` | Các lớp trực tiếp trong package `com.example.dto`. |
| `com.example.dto.**` | Các lớp trong package đó và các package con. |
| `!*` | Từ chối mọi lớp chưa được pattern trước đó chấp nhận. |
| `*` | Khớp mọi lớp. |

`package.*` và `package.**` không giống nhau. Nếu DTO được chia trong các package con như `com.example.dto.order`, pattern `com.example.dto.*` không bao quát cùng phạm vi với `com.example.dto.**`.

### 5.2. Vì sao nên có !* ở cuối allowlist?

Một pattern chỉ chứa các lớp được phép có thể trả về `UNDECIDED` cho lớp không khớp. `UNDECIDED` không có nghĩa là từ chối. Khi cần một allowlist thực sự, cần có quy tắc từ chối cuối cùng để những lớp không nằm trong danh sách bị loại.

Ví dụ:

```text
com.example.dto.**;java.lang.String;!*
```

Không nên bỏ `!*` rồi cho rằng mọi lớp chưa khớp tự động bị chặn.

### 5.3. Allowlist phải phản ánh toàn bộ đồ thị hợp lệ

Một DTO có thể chứa collection, enum, date/time hoặc các lớp hỗ trợ khác. Nếu chỉ allowlist DTO gốc, filter có thể từ chối một lớp con cần thiết khi stream khôi phục đồ thị.

Ví dụ, nếu DTO có trường `ArrayList<String>`, ứng dụng cần đánh giá và cho phép kiểu collection cần thiết cùng những kiểu phần tử liên quan. Không nên thêm cả package `java.util.**` một cách tùy tiện chỉ để làm cho request chạy được; điều đó mở rộng tập kiểu đáng kể.

Hãy xác định các lớp thực sự được serialize trong hợp đồng dữ liệu, rồi thêm từng lớp hoặc package hẹp. Test với các payload hợp lệ đại diện cho những nhánh dữ liệu cần hỗ trợ.

## 6. Cấu hình filter bằng pattern string

`ObjectInputFilter.Config.createFilter(String)` tạo filter từ chuỗi pattern. Đây là cách ngắn gọn để cấu hình ngưỡng và class pattern.

Ví dụ:

```java
import java.io.ObjectInputFilter;

ObjectInputFilter filter = ObjectInputFilter.Config.createFilter(
        "maxdepth=20;" +
        "maxrefs=1000;" +
        "maxbytes=1048576;" +
        "maxarray=10000;" +
        "com.example.dto.**;" +
        "java.lang.String;" +
        "!*"
);
```

Pattern này:

1. Từ chối stream vượt bất kỳ giới hạn tài nguyên nào.
2. Cho phép các lớp DTO trong package được chỉ định.
3. Cho phép `String`.
4. Từ chối lớp khác không khớp.

Đây là cấu hình mẫu. Nếu đồ thị có `ArrayList`, enum hoặc kiểu hỗ trợ khác, phải bổ sung chúng theo đúng hợp đồng dữ liệu. Không nên thay `!*` bằng `*` chỉ để bỏ lỗi từ chối; làm vậy sẽ mất ý nghĩa allowlist.

### 6.1. Các giá trị giới hạn

Giá trị của các thuộc tính giới hạn là số không âm:

- `maxdepth=n`
- `maxrefs=n`
- `maxbytes=n`
- `maxarray=n`

Nên ghi đơn vị và ý nghĩa trong cấu hình triển khai. Ví dụ `maxbytes=1048576` là byte, không phải KB hay số object.

### 6.2. Pattern không thay thế kiểm tra nghiệp vụ

Một lớp `com.example.dto.PaymentRequest` có thể được allowlist nhưng vẫn chứa:

- Số tiền âm hoặc vượt giới hạn nghiệp vụ.
- Mã khách hàng không hợp lệ.
- Trạng thái không được phép.
- Chuỗi dài hơn giới hạn nghiệp vụ.

Filter quyết định kiểu và giới hạn cấu trúc/stream; sau khi đọc object, ứng dụng vẫn phải kiểm tra các giá trị và quan hệ nghiệp vụ.

## 7. Gắn filter cho từng ObjectInputStream

Nếu chỉ một luồng nhận dữ liệu cần filter riêng, có thể dùng `ObjectInputStream.setObjectInputFilter(...)`.

Ví dụ:

```java
import java.io.IOException;
import java.io.InputStream;
import java.io.ObjectInputFilter;
import java.io.ObjectInputStream;

public class FilteredReader {
    static Object read(InputStream source)
            throws IOException, ClassNotFoundException {

        ObjectInputFilter filter = ObjectInputFilter.Config.createFilter(
                "maxdepth=20;" +
                "maxrefs=1000;" +
                "maxbytes=1048576;" +
                "maxarray=10000;" +
                "com.example.dto.**;" +
                "java.lang.String;" +
                "!*"
        );

        try (ObjectInputStream input = new ObjectInputStream(source)) {
            input.setObjectInputFilter(filter);
            return input.readObject();
        }
    }
}
```

Filter cần được cài đặt **trước khi đọc object**. Sau khi stream đã bắt đầu giải tuần tự hóa, không nên đợi tới lúc đã đọc một phần dữ liệu mới đặt filter.

Phương thức trên trả `Object` để minh họa API. Ở tầng ứng dụng, nên kiểm tra kiểu kết quả:

```java
import java.io.InvalidObjectException;

Object value = FilteredReader.read(source);
if (!(value instanceof CustomerDto customer)) {
    throw new InvalidObjectException("Kiểu dữ liệu không được hỗ trợ");
}
```

Kiểm tra kiểu kết quả không thay thế filter; nó là bước xác nhận hợp đồng sau khi object đã được đọc.

### 7.1. Phạm vi của per-stream filter

Per-stream filter phù hợp khi:

- Một endpoint nhận một loại message cụ thể.
- Một luồng import có giới hạn riêng.
- Các nguồn dữ liệu khác nhau có allowlist và ngân sách khác nhau.

Ưu điểm là mỗi luồng có thể có chính sách sát với dữ liệu của nó. Nhược điểm là mọi nơi tạo `ObjectInputStream` phải được cấu hình đúng; bỏ sót một điểm đọc sẽ tạo ra đường vào không được bảo vệ.

## 8. Viết filter bằng lambda để kiểm soát chi tiết

Pattern string tiện cho cấu hình, nhưng filter tùy chỉnh cho phép viết logic rõ ràng hơn, nhất là khi cần xử lý array class hoặc điều kiện theo kiểu.

Ví dụ giới hạn tài nguyên:

```java
import java.io.ObjectInputFilter;

static ObjectInputFilter resourceFilter() {
    return info -> {
        if (info.depth() > 20
                || info.references() > 1_000
                || info.streamBytes() > 1_048_576
                || (info.arrayLength() >= 0
                    && info.arrayLength() > 10_000)) {
            return ObjectInputFilter.Status.REJECTED;
        }

        return ObjectInputFilter.Status.UNDECIDED;
    };
}
```

Filter này chỉ đặt giới hạn tài nguyên; nó không tự allowlist lớp. Khi dùng độc lập, `UNDECIDED` không phải là quy tắc từ chối tất cả lớp chưa biết. Cần kết hợp class filter nếu muốn giới hạn kiểu.

### 8.1. Kết hợp giới hạn với allowlist lớp

Ví dụ có một lớp DTO:

```java
import java.io.Serializable;

public final class CustomerDto implements Serializable {
    private static final long serialVersionUID = 1L;

    private final String name;
    private final int age;

    public CustomerDto(String name, int age) {
        this.name = name;
        this.age = age;
    }
}
```

Filter có thể kiểm tra cả ngưỡng và kiểu:

```java
import java.io.ObjectInputFilter;

static ObjectInputFilter customerFilter() {
    return info -> {
        if (info.depth() > 20
                || info.references() > 1_000
                || info.streamBytes() > 1_048_576
                || (info.arrayLength() >= 0
                    && info.arrayLength() > 10_000)) {
            return ObjectInputFilter.Status.REJECTED;
        }

        Class<?> type = info.serialClass();
        if (type == null) {
            return ObjectInputFilter.Status.UNDECIDED;
        }

        while (type.isArray()) {
            type = type.getComponentType();
        }

        if (type.isPrimitive()
                || type == String.class
                || type == CustomerDto.class) {
            return ObjectInputFilter.Status.ALLOWED;
        }

        return ObjectInputFilter.Status.REJECTED;
    };
}
```

Đoạn code minh họa cách:

- Từ chối khi một trong bốn giới hạn bị vượt.
- Xử lý `serialClass()` có thể là `null`.
- Bóc các chiều array để kiểm tra component type.
- Chỉ cho phép primitive component, `String` và DTO đã chọn.
- Từ chối các lớp khác.

Trong một ứng dụng thật, hãy mở rộng allowlist cho đúng các kiểu được sử dụng trong đồ thị serialized. Ví dụ DTO có enum, collection hoặc một lớp value riêng thì các kiểu đó cần được xem xét có chủ đích.

### 8.2. Vì sao serialClass() có thể là null?

Không phải mọi lần gọi filter đều gắn với một lớp mới. Khi `serialClass()` là `null`, filter không có tên lớp để so khớp. Có thể vẫn đánh giá các ngưỡng tài nguyên trước; nếu chúng không vượt thì trả `UNDECIDED` để không tự gán một lớp giả định.

Không nên trả `ALLOWED` ngay khi `serialClass()` là null trước khi kiểm tra depth/references/bytes/arrayLength. Những thông tin tài nguyên vẫn có thể cần được áp dụng.
 
## 9. Cấu hình filter toàn JVM

Nếu ứng dụng có nhiều điểm sử dụng `ObjectInputStream`, có thể thiết lập process-wide filter.

### 9.1. Dùng system property jdk.serialFilter

Có thể cấu hình khi khởi chạy JVM:

```bash
java "-Djdk.serialFilter=maxdepth=20;maxrefs=1000;maxbytes=1048576;maxarray=10000;com.example.dto.**;java.lang.String;!*" -jar app.jar
```

Filter toàn JVM giúp áp dụng chính sách chung cho các stream được tạo trong tiến trình theo cơ chế cấu hình của JDK. Hãy kiểm tra cách shell truyền dấu chấm phẩy và dấu nháy trên hệ điều hành triển khai; ví dụ trên đặt toàn bộ pattern thành một giá trị property.

### 9.2. Dùng Config.setSerialFilter

Có thể thiết lập filter process-wide bằng API:

```java
ObjectInputFilter global = ObjectInputFilter.Config.createFilter(
        "maxdepth=20;maxrefs=1000;maxbytes=1048576;maxarray=10000;com.example.dto.**;java.lang.String;!*"
);

ObjectInputFilter.Config.setSerialFilter(global);
```

Đây là cấu hình toàn tiến trình và chỉ có thể thiết lập theo quy tắc một lần của API; nếu một filter toàn cục đã được thiết lập, việc thiết lập lại có thể thất bại với `IllegalStateException`. Nên cấu hình sớm trong giai đoạn khởi động, trước khi các thành phần bắt đầu deserialization.

### 9.3. Global filter và per-stream filter

Global filter hữu ích làm chính sách nền; per-stream filter hữu ích khi một endpoint cần chính sách riêng. Cơ chế chọn/kết hợp filter của JVM còn chịu ảnh hưởng của filter factory. Không nên mặc định hai filter luôn được ghép theo phép AND hoặc filter cục bộ luôn thay thế filter toàn cục trong mọi cấu hình.

Trên Java 17, `ObjectInputFilter.Config.getSerialFilterFactory()` và filter factory cho phép ứng dụng kiểm soát cách chọn filter cho từng stream. Nếu ứng dụng cần kết hợp nhiều chính sách, hãy cấu hình và kiểm tra factory một cách rõ ràng thay vì dựa vào thứ tự ngầm định.

## 10. Filter factory và chính sách theo ngữ cảnh

JEP 415 được đưa vào Java 17 để hỗ trợ **context-specific deserialization filters**. Một ứng dụng lớn có thể có nhiều loại dữ liệu và nguồn gọi khác nhau; một chính sách duy nhất có thể quá rộng cho endpoint này nhưng quá chặt cho endpoint khác.

Filter factory cho phép chọn filter khi một `ObjectInputStream` được tạo, dựa trên filter hiện tại, filter được yêu cầu và ngữ cảnh mà ứng dụng quản lý.

Các trường hợp có thể cần chính sách riêng:

- Message nội bộ từ dịch vụ đã xác thực.
- File import do người dùng tải lên.
- Cache cục bộ được tạo bởi cùng phiên bản ứng dụng.
- Dữ liệu tương thích với một integration legacy.

Không nên dùng một allowlist rộng chung cho tất cả nguồn chỉ vì tiện cấu hình. Mỗi nguồn có hợp đồng dữ liệu và ngân sách khác nhau; filter factory giúp đưa ra quyết định phù hợp với ngữ cảnh.

JEP 415 không thay đổi ý nghĩa của bốn ngưỡng `maxdepth`, `maxrefs`, `maxbytes`, `maxarray`; nó bổ sung cách chọn filter linh hoạt hơn.

## 11. Chọn ngưỡng theo dữ liệu thật

Các con số trong ví dụ không phải mặc định an toàn. Cách chọn ngưỡng nên dựa vào hợp đồng message:

| Giới hạn | Câu hỏi cần trả lời |
| --- | --- |
| `maxdepth` | DTO hợp lệ lồng nhau sâu tối đa bao nhiêu cấp? |
| `maxrefs` | Một request hợp lệ có tối đa bao nhiêu object/reference? |
| `maxbytes` | Payload serialized lớn nhất theo nghiệp vụ là bao nhiêu byte? |
| `maxarray` | Mảng hợp lệ lớn nhất có bao nhiêu phần tử? |
| Class allowlist | Chính xác những lớp nào có thể xuất hiện trong đồ thị? |

Quy trình chọn ngưỡng:

1. Lấy các payload hợp lệ đại diện cho kích thước nhỏ, trung bình và lớn.
2. Đo depth, references, streamBytes và arrayLength trong filter callback.
3. Xác định mức tối đa theo yêu cầu nghiệp vụ.
4. Thêm khoảng dự phòng có kiểm soát cho dữ liệu hợp lệ.
5. Thử payload ngay dưới ngưỡng và vượt từng ngưỡng.
6. Theo dõi số lần từ chối trong môi trường chạy để điều chỉnh có căn cứ.

Không nên đặt một con số rất lớn chỉ để tránh lỗi. Ngưỡng phải có liên hệ với dữ liệu tối đa mà hệ thống thật sự cần xử lý.

### 11.1. Mỗi giới hạn bảo vệ một dạng tăng trưởng

| Dạng payload | Giới hạn đáng chú ý |
| --- | --- |
| Chuỗi object lồng nhau rất sâu | `maxdepth` |
| Danh sách nhiều object nhỏ | `maxrefs` |
| Nhiều dữ liệu serialized hoặc field lớn | `maxbytes` |
| Một mảng rất dài | `maxarray` |
| Lớp ngoài hợp đồng dữ liệu | Class allowlist |

Một payload có thể vượt nhiều giới hạn cùng lúc. Filter chỉ cần từ chối khi bất kỳ điều kiện bắt buộc nào bị vi phạm.

## 12. Phân biệt giới hạn mảng với giới hạn nội dung chuỗi

`maxarray` kiểm soát chiều dài mảng Java, không phải số ký tự của mọi `String`.

Nếu ứng dụng cần giới hạn độ dài trường văn bản như tên, ghi chú hoặc nội dung mô tả, hãy kiểm tra sau khi deserialization:

```java
if (customer.getName() == null
        || customer.getName().length() > 200) {
    throw new IllegalArgumentException("Tên không hợp lệ");
}
```

Nếu cần giới hạn số byte đầu vào, áp dụng giới hạn ở tầng transport hoặc stream wrapper bên cạnh `maxbytes`. Nếu cần giới hạn độ dài chuỗi theo byte UTF-8, phải đo bằng charset tương ứng; `String.length()` đếm đơn vị UTF-16 code unit, không phải số byte UTF-8.

Các loại giới hạn không thể thay thế nhau:

- `maxarray`: số phần tử của một array.
- `maxbytes`: byte đã đọc từ serialization stream.
- `String.length()`: độ dài theo UTF-16 code unit.
- `getBytes(UTF_8).length`: số byte của chuỗi khi mã hóa UTF-8.

## 13. Từ chối dữ liệu và xử lý ngoại lệ

Khi filter trả `REJECTED`, quá trình đọc object bị hủy. Ứng dụng thường nhận `InvalidClassException`, là một `ObjectStreamException`/`IOException`.

Ví dụ:

```java
import java.io.IOException;
import java.io.InvalidClassException;
import java.io.ObjectInputStream;

try (ObjectInputStream input = new ObjectInputStream(source)) {
    input.setObjectInputFilter(filter);
    Object value = input.readObject();
    // Xử lý value sau khi đã xác nhận kiểu và dữ liệu.
} catch (InvalidClassException ex) {
    System.out.println("Dữ liệu bị serialization filter từ chối");
} catch (IOException | ClassNotFoundException ex) {
    System.out.println("Không thể đọc dữ liệu: " + ex.getMessage());
}
```

Không nên trả về cho caller thông tin chi tiết nội bộ về class hoặc cấu trúc filter nếu điều đó làm lộ thông tin không cần thiết. Log nội bộ có thể ghi nguyên nhân phù hợp để điều tra, nhưng tránh log toàn bộ payload nhạy cảm.

`REJECTED` không nên bị bắt rồi bỏ qua để tiếp tục dùng một object dở dang. Khi stream bị từ chối, hãy xem toàn bộ message là không hợp lệ và kết thúc xử lý request đó.

## 14. Những gì serialization filter không làm

`ObjectInputFilter` có phạm vi cụ thể. Nó không thay thế:

- **Xác thực nghiệp vụ:** số tiền, trạng thái, mã định danh và quan hệ giữa các trường vẫn cần kiểm tra.
- **Giới hạn đầu vào ở tầng mạng/file:** giới hạn payload trước khi tạo object stream vẫn cần thiết.
- **Xác thực nguồn gửi:** filter không chứng minh ai đã gửi dữ liệu.
- **Kiểm tra tính toàn vẹn:** nếu giao thức cần xác thực nguồn gốc/tính toàn vẹn, dùng cơ chế phù hợp như MAC hoặc chữ ký theo thiết kế hệ thống.
- **Thiết kế API an toàn:** allowlist lớp không biến một lớp có `readObject` nguy hiểm thành lớp an toàn.
- **Giới hạn thời gian xử lý:** các ngưỡng graph không phải timeout CPU hoặc timeout I/O.

Nếu có thể thay native Java serialization bằng định dạng dữ liệu có schema rõ ràng và parser phù hợp, đó thường là hướng thiết kế dễ kiểm soát hơn cho giao tiếp mới. Nếu phải duy trì Java serialization, hãy dùng filter với allowlist và ngưỡng phù hợp.

## 15. Ví dụ tổng hợp: đọc một DTO với giới hạn

Ví dụ sau minh họa một DTO đơn giản và filter cho một loại message cụ thể.

```java
import java.io.IOException;
import java.io.InputStream;
import java.io.InvalidClassException;
import java.io.InvalidObjectException;
import java.io.ObjectInputFilter;
import java.io.ObjectInputStream;
import java.io.Serializable;

public class SafeMessageReader {

    public static final class Message implements Serializable {
        private static final long serialVersionUID = 1L;

        private final String id;
        private final String body;

        public Message(String id, String body) {
            this.id = id;
            this.body = body;
        }

        public String id() {
            return id;
        }

        public String body() {
            return body;
        }
    }

    private static ObjectInputFilter filter() {
        return info -> {
            if (info.depth() > 10
                    || info.references() > 100
                    || info.streamBytes() > 256 * 1024
                    || (info.arrayLength() >= 0
                        && info.arrayLength() > 2_000)) {
                return ObjectInputFilter.Status.REJECTED;
            }

            Class<?> type = info.serialClass();
            if (type == null) {
                return ObjectInputFilter.Status.UNDECIDED;
            }

            while (type.isArray()) {
                type = type.getComponentType();
            }

            if (type.isPrimitive()
                    || type == String.class
                    || type == Message.class) {
                return ObjectInputFilter.Status.ALLOWED;
            }

            return ObjectInputFilter.Status.REJECTED;
        };
    }

    public static Message read(InputStream source)
            throws IOException, ClassNotFoundException {
        try (ObjectInputStream input = new ObjectInputStream(source)) {
            input.setObjectInputFilter(filter());
            Object value = input.readObject();

            if (!(value instanceof Message message)) {
                throw new InvalidObjectException(
                        "Expected SafeMessageReader.Message"
                );
            }

            if (message.id() == null || message.id().length() > 64) {
                throw new InvalidObjectException("Message id is invalid");
            }
            if (message.body() == null || message.body().length() > 10_000) {
                throw new InvalidObjectException("Message body is invalid");
            }

            return message;
        }
    }
}
```

Trong ví dụ:

- Độ sâu tối đa là 10.
- Số tham chiếu tối đa là 100.
- Byte đọc từ serialization stream tối đa là 256 KiB.
- Mảng tối đa 2.000 phần tử.
- Chỉ cho phép `Message`, `String` và kiểu primitive/array primitive tương ứng.
- Sau khi đọc, ứng dụng vẫn kiểm tra kiểu gốc và giới hạn độ dài nghiệp vụ của `id` và `body`.

Các ngưỡng nhỏ chỉ phù hợp với ví dụ message này. Khi thay đổi DTO hoặc thêm collection/enum/kiểu lồng nhau, phải cập nhật allowlist và ngân sách theo hợp đồng mới.

## 16. Lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `InvalidClassException` khi đọc object hợp lệ | Filter từ chối lớp cần thiết hoặc một ngưỡng đặt quá thấp. | Xem class và các chỉ số FilterInfo; chỉ thêm kiểu/ngưỡng thật sự cần. |
| Đã đặt `maxdepth` nhưng payload có quá nhiều object vẫn lọt | Đồ thị rộng nhưng không sâu. | Bổ sung `maxrefs`. |
| Đã đặt `maxrefs` nhưng payload vẫn đọc quá nhiều byte | Số object có thể ít nhưng dữ liệu serialized lớn. | Bổ sung `maxbytes` và giới hạn payload ở tầng transport. |
| Đã đặt `maxbytes` nhưng mảng lớn vẫn cần giới hạn riêng | Ngân sách byte và số phần tử mảng là hai đại lượng khác nhau. | Bổ sung `maxarray`. |
| Allowlist không khớp với package con | Dùng `package.*` trong khi lớp nằm ở package con. | Dùng `package.**` nếu toàn bộ package con thực sự thuộc hợp đồng cho phép. |
| Lớp không khớp vẫn chưa bị từ chối | Pattern không khớp trả `UNDECIDED`. | Thêm `!*` ở cuối allowlist hoặc trả `REJECTED` trong custom filter. |
| DTO được phép nhưng collection bên trong bị chặn | Đồ thị còn chứa lớp collection/enum/value khác. | Xác định kiểu serialized thực tế và allowlist chính xác. |
| Filter chỉ được đặt sau `readObject()` | Object đã được giải tuần tự hóa trước khi filter được cài. | Cài filter ngay sau khi tạo `ObjectInputStream` và trước khi đọc object. |
| `maxarray` không giới hạn độ dài `String` như mong đợi | String không phải mảng Java trong ý nghĩa của ngưỡng này. | Kiểm tra độ dài chuỗi sau khi đọc và giới hạn byte ở tầng stream/transport. |
| Global filter ảnh hưởng nhiều luồng hơn dự kiến | Filter toàn JVM có phạm vi process-wide. | Dùng chính sách theo ngữ cảnh hoặc per-stream phù hợp; quản lý filter factory khi cần. |
| Nghĩ filter bảo vệ mọi khía cạnh deserialization | Filter không xác thực giá trị nghiệp vụ, nguồn gửi hoặc thời gian xử lý. | Kết hợp validation, xác thực nguồn và giới hạn ở các tầng khác. |

## 17. Bài tập thực hành

### Bài 1 — Áp dụng bốn giới hạn

Tạo filter pattern:

```text
maxdepth=10;maxrefs=500;maxbytes=524288;maxarray=5000;*
```

Giải thích từng ngưỡng và vì sao pattern `*` không tạo allowlist lớp.

### Bài 2 — Viết allowlist

Tạo filter chỉ cho phép các lớp trong `com.example.dto` và `java.lang.String`, đồng thời từ chối tất cả lớp khác. Thử bỏ `!*` và giải thích sự khác nhau giữa `UNDECIDED` và `REJECTED`.

### Bài 3 — Độ sâu và số tham chiếu

Tạo hai đồ thị:

- Một chuỗi object lồng nhau sâu.
- Một object gốc tham chiếu đến nhiều object con.

Quan sát vì sao `maxdepth` và `maxrefs` phát hiện hai dạng tăng trưởng khác nhau.

### Bài 4 — Kích thước mảng

Serialize một DTO có `byte[]` với độ dài dưới và trên ngưỡng `maxarray`. Quan sát filter nhận `arrayLength()` và giải thích vì sao giới hạn này không đồng nghĩa với giới hạn byte toàn stream.

### Bài 5 — Per-stream và global filter

Viết một reader dùng `setObjectInputFilter`, sau đó tìm hiểu cách cấu hình process-wide bằng `jdk.serialFilter`. Nêu tình huống phù hợp cho từng phạm vi.

### Bài 6 — Kiểm tra sau deserialization

Tạo DTO có trường `name` và `amount`. Dùng filter giới hạn class/graph, rồi kiểm tra `name` không null, độ dài không vượt ngưỡng và `amount` không âm. Giải thích vì sao filter không thay thế validation nghiệp vụ.

## 18. Tài liệu Java 17 chính thức

- [Java SE 17 API — ObjectInputFilter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputFilter.html): filter interface, FilterInfo, Status và các chỉ số của đồ thị.
- [Java SE 17 API — ObjectInputFilter.Config](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputFilter.Config.html): tạo filter từ pattern, cấu hình process-wide filter và filter factory.
- [Java SE 17 API — ObjectInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputStream.html): cài per-stream filter và đọc object.
- [Java SE 17 Launcher — jdk.serialFilter](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): cấu hình filter qua JVM system property.
- [JEP 290 — Filter Incoming Serialization Data](https://openjdk.org/jeps/290): thiết kế serialization filter, giới hạn tài nguyên và lọc lớp.
- [JEP 415 — Context-Specific Deserialization Filters](https://openjdk.org/jeps/415): filter factory và chính sách deserialization theo ngữ cảnh, được đưa vào JDK 17.

Khi lọc giải tuần tự hóa trong Java 17, hãy kết hợp **allowlist lớp** với bốn ngưỡng độc lập: `maxdepth`, `maxrefs`, `maxbytes` và `maxarray`. Độ sâu giới hạn mức lồng nhau; số tham chiếu giới hạn độ rộng đồ thị; số byte giới hạn dữ liệu đã đọc; kích thước mảng giới hạn từng array. Cấu hình filter trước khi đọc object, đặt ngưỡng theo payload hợp lệ thực tế và tiếp tục xác thực giá trị sau khi giải tuần tự hóa.
