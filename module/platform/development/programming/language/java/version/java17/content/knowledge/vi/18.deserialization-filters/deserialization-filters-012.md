# Kiểm thử từ chối, tài nguyên quá mức và chính sách theo ngữ cảnh khi giải tuần tự hóa trong Java 17

**Chủ đề:** Java 17  
**Chương:** Lọc giải tuần tự hóa  
**Bài học:** Kiểm thử từ chối, tài nguyên quá mức và chính sách theo ngữ cảnh

Java serialization có thể tái tạo object graph từ một luồng byte. Khi dữ liệu đến từ bên ngoài ranh giới tin cậy, việc gọi `ObjectInputStream.readObject()` mà không giới hạn có thể khiến ứng dụng khởi tạo những lớp không mong muốn hoặc tiêu thụ quá nhiều bộ nhớ, CPU và tài nguyên khác.

Java cung cấp **serialization filter** qua `java.io.ObjectInputFilter` để kiểm soát quá trình giải tuần tự hóa. Filter có thể xem lớp đang được đọc và các chỉ số của object graph như độ sâu, số tham chiếu, kích thước mảng và số byte đã đọc. Nó có thể chấp nhận, từ chối hoặc để một filter khác quyết định.

Java 17 còn có filter factory theo ngữ cảnh, được chuẩn hóa qua JEP 415. Factory cho phép chọn hoặc kết hợp chính sách phù hợp với từng luồng giải tuần tự hóa, ví dụ theo chức năng ứng dụng, module, class loader hoặc ngữ cảnh request.

Bài học này tập trung vào ba việc cần làm trong một hệ thống thực tế:

- **Kiểm thử từ chối:** chứng minh dữ liệu có lớp không được phép sẽ bị từ chối trước khi ứng dụng sử dụng object.
- **Giới hạn tài nguyên:** đặt ngưỡng cho depth, references, array length và stream bytes để giảm nguy cơ tiêu thụ tài nguyên quá mức.
- **Chính sách theo ngữ cảnh:** áp dụng allowlist và giới hạn khác nhau cho từng loại dữ liệu, đồng thời vẫn giữ chính sách nền của ứng dụng.

Filter là một lớp phòng vệ quan trọng, nhưng không biến Java native serialization thành định dạng an toàn cho dữ liệu không tin cậy. Nếu có thể, ưu tiên định dạng dữ liệu có schema và parser được thiết kế cho đầu vào bên ngoài.

## 1. Serialization filter kiểm soát điều gì?

Một object được serialize có thể chứa tham chiếu tới nhiều object khác. Khi gọi `readObject()`, `ObjectInputStream` dựng lại đồ thị object (*object graph*) từ luồng dữ liệu.

Ví dụ một thông điệp đơn giản:

```java
import java.io.Serializable;

public final class Message implements Serializable {
    private static final long serialVersionUID = 1L;

    private final String text;

    public Message(String text) {
        this.text = text;
    }

    public String text() {
        return text;
    }
}
```

Một object `Message` có thể tham chiếu tới `String`; một object khác có thể chứa list, map, mảng hoặc các object lồng nhau. Nếu ứng dụng không giới hạn loại class và kích thước đồ thị, dữ liệu đầu vào có thể yêu cầu xử lý một cấu trúc vượt quá nhu cầu nghiệp vụ.

`ObjectInputFilter` được gọi trong quá trình giải tuần tự hóa để đưa ra quyết định dựa trên thông tin của đối tượng đang được xử lý.

### 1.1. Ba trạng thái của filter

`ObjectInputFilter.Status` có ba giá trị:

| Trạng thái | Ý nghĩa |
|---|---|
| `ALLOWED` | Filter này cho phép đối tượng/điều kiện hiện tại |
| `REJECTED` | Filter này từ chối; quá trình đọc bị dừng |
| `UNDECIDED` | Filter này chưa đưa ra quyết định |

`UNDECIDED` không có nghĩa là đã được xác nhận an toàn. Nó chỉ nói rằng filter hiện tại không quyết định. Một filter khác, filter tổng hợp hoặc hành vi mặc định của stream có thể tiếp tục quyết định.

Vì vậy, một allowlist nghiêm ngặt cần xử lý rõ các class không nằm trong danh sách. Trong Java 17 có thể dùng `ObjectInputFilter.rejectUndecidedClass(filter)` để chuyển kết quả `UNDECIDED` cho class thành `REJECTED`.

### 1.2. Thông tin filter nhận được

`ObjectInputFilter.FilterInfo` cung cấp những thông tin chính:

| Phương thức | Thông tin | Giá trị đặc biệt |
|---|---|---|
| `serialClass()` | Class đang được giải tuần tự hóa | Có thể là `null` khi không có class mới để xét |
| `arrayLength()` | Độ dài mảng hiện tại | `-1` nếu đối tượng hiện tại không phải mảng |
| `depth()` | Độ sâu hiện tại của object graph | Số lớn hơn biểu thị cấu trúc lồng sâu hơn |
| `references()` | Số tham chiếu object đã được xử lý | Tăng theo quá trình đọc stream |
| `streamBytes()` | Số byte đã đọc từ stream | Tổng byte đã tiêu thụ tại thời điểm kiểm tra |

Các chỉ số này giúp filter giới hạn cả **loại dữ liệu** lẫn **quy mô dữ liệu**. Không nên giả định `serialClass()` luôn khác null; filter cần xử lý trường hợp không có class để quyết định.

## 2. Đặt giới hạn tài nguyên

Một filter có thể từ chối object graph khi vượt một trong các ngưỡng:

- Độ sâu tối đa: tránh cấu trúc lồng nhau quá sâu.
- Số tham chiếu tối đa: giới hạn số object reference mà stream yêu cầu xử lý.
- Kích thước mảng tối đa: tránh mảng có số phần tử vượt khả năng nghiệp vụ.
- Số byte tối đa: giới hạn lượng dữ liệu serialization đã tiêu thụ.

Ví dụ một policy giới hạn tài nguyên:

```java
import java.io.ObjectInputFilter;

final class SerializationLimits {
    static final long MAX_DEPTH = 20;
    static final long MAX_REFERENCES = 10_000;
    static final long MAX_ARRAY_LENGTH = 100_000;
    static final long MAX_STREAM_BYTES = 1_048_576; // 1 MiB

    static final ObjectInputFilter FILTER = info -> {
        if (info.depth() > MAX_DEPTH
                || info.references() > MAX_REFERENCES
                || info.arrayLength() > MAX_ARRAY_LENGTH
                || info.streamBytes() > MAX_STREAM_BYTES) {
            return ObjectInputFilter.Status.REJECTED;
        }

        return ObjectInputFilter.Status.UNDECIDED;
    };
}
```

Filter trả về `REJECTED` khi bất kỳ ngưỡng nào bị vượt. Nếu không vượt, nó trả `UNDECIDED` để một chính sách khác có thể kiểm tra class.

Các con số trên chỉ là ví dụ. Hạn mức thực tế phải dựa trên kích thước payload hợp lệ, cấu trúc object graph, bộ nhớ khả dụng và yêu cầu nghiệp vụ. Không có một bộ ngưỡng phù hợp cho mọi ứng dụng.

### 2.1. Vì sao cần nhiều giới hạn cùng lúc?

Chỉ giới hạn stream bytes là chưa đủ:

- Một payload không quá lớn vẫn có thể chứa đồ thị lồng rất sâu.
- Một mảng có thể khai báo số phần tử lớn và tạo áp lực bộ nhớ.
- Nhiều object nhỏ có thể làm số tham chiếu tăng rất nhanh.
- Một cấu trúc lồng sâu có thể làm tăng chi phí xử lý hoặc gây tràn stack ở code phía ứng dụng.

Kết hợp nhiều chỉ số giúp policy phản ánh nhiều kiểu tiêu thụ tài nguyên khác nhau.

### 2.2. Ý nghĩa của phép so sánh ngưỡng

Các điều kiện thường dùng là `> MAX`, nghĩa là cho phép giá trị đúng bằng ngưỡng và từ chối khi vượt ngưỡng.

Ví dụ, với `MAX_DEPTH = 20`:

- `depth() == 20`: chưa vượt giới hạn.
- `depth() == 21`: bị từ chối.

Hãy ghi rõ trong tài liệu cấu hình rằng ngưỡng là giới hạn trên bao gồm giá trị bằng ngưỡng. Nếu nghiệp vụ muốn từ chối ngay khi chạm ngưỡng, điều kiện sẽ khác.

### 2.3. Giới hạn không thay thế giới hạn ở tầng giao thức

`streamBytes()` đo byte đã được `ObjectInputStream` tiêu thụ tại thời điểm filter được gọi. Ứng dụng vẫn nên giới hạn kích thước request hoặc file trước khi bắt đầu deserialize, ví dụ giới hạn upload ở HTTP server hoặc kiểm tra kích thước file.

Cần áp dụng phòng vệ theo nhiều tầng:

1. Giới hạn kích thước đầu vào trước khi tạo stream.
2. Giới hạn depth, references, array và stream bytes bằng serialization filter.
3. Chỉ cho phép các class cần thiết.
4. Kiểm tra dữ liệu nghiệp vụ sau khi deserialize.
5. Áp dụng timeout và giới hạn tài nguyên ở tầng request/worker nếu công việc có thể tốn thời gian.

Filter không phải bộ giới hạn CPU tổng quát và không thể thay thế timeout, quota hoặc giới hạn bộ nhớ của tiến trình.


## 3. Kiểm soát class bằng allowlist

Giới hạn tài nguyên không đủ nếu mọi class đều được phép. Policy nên chỉ chấp nhận các class mà giao thức dữ liệu thực sự cần.

Ví dụ, một endpoint chỉ nhận `Message` với trường `String`. Ta có thể viết filter cho phép hai class này và từ chối class khác.

```java
import java.io.ObjectInputFilter;
import java.util.Set;

final class MessagePolicy {
    private static final Set<Class<?>> ALLOWED =
            Set.of(Message.class, String.class);

    static final ObjectInputFilter FILTER = info -> {
        Class<?> type = info.serialClass();

        if (type == null) {
            return ObjectInputFilter.Status.UNDECIDED;
        }

        if (ALLOWED.contains(type)) {
            return ObjectInputFilter.Status.ALLOWED;
        }

        return ObjectInputFilter.Status.REJECTED;
    };
}
```

Allowlist chính xác thường dễ kiểm soát hơn denylist. Denylist chỉ loại bỏ những class đã biết là nguy hiểm; một class mới hoặc class lồng trong object graph có thể vẫn lọt qua.

### 3.1. Xử lý mảng trong allowlist

Nếu giao thức cho phép mảng, cần quyết định rõ loại phần tử nào được chấp nhận. Không nên cho phép mọi mảng chỉ vì class của nó là array.

Ví dụ chấp nhận mảng primitive và mảng String:

```java
static boolean isAllowedArray(Class<?> type) {
    if (!type.isArray()) {
        return false;
    }

    Class<?> component = type;
    while (component.isArray()) {
        component = component.getComponentType();
    }

    return component.isPrimitive() || component == String.class;
}
```

Khi kết hợp với kiểm tra class:

```java
static ObjectInputFilter classFilter() {
    return info -> {
        Class<?> type = info.serialClass();

        if (type == null) {
            return ObjectInputFilter.Status.UNDECIDED;
        }

        if (ALLOWED.contains(type) || isAllowedArray(type)) {
            return ObjectInputFilter.Status.ALLOWED;
        }

        return ObjectInputFilter.Status.REJECTED;
    };
}
```

Mảng vẫn phải chịu giới hạn `arrayLength()`. Chấp nhận kiểu `byte[]` không có nghĩa cho phép mảng byte với kích thước tùy ý.

### 3.2. Allowlist phải phản ánh toàn bộ object graph

Khi một class được phép có field tham chiếu tới class khác, class đó cũng cần được xem xét. Ví dụ `Message` có thể tham chiếu `String`; một DTO khác có thể chứa `List`, phần tử list, enum hoặc mảng.

Không nên thêm rộng toàn bộ package thư viện chuẩn chỉ để làm ví dụ deserialize chạy được. Hãy xác định chính xác cấu trúc cần thiết và kiểm thử object graph hợp lệ thực tế.

## 4. Kết hợp filter bằng API Java 17

Java 17 cung cấp hai phương thức tĩnh hữu ích trên `ObjectInputFilter`:

- `merge(filterA, filterB)`: kết hợp hai filter.
- `rejectUndecidedClass(filter)`: từ chối class nếu filter bên trong trả về `UNDECIDED`.

Quy tắc kết hợp của `merge`:

- Nếu một filter trả `REJECTED`, kết quả là `REJECTED`.
- Nếu không filter nào từ chối và ít nhất một filter trả `ALLOWED`, kết quả là `ALLOWED`.
- Nếu cả hai đều `UNDECIDED`, kết quả là `UNDECIDED`.

Nhờ vậy có thể tách policy thành hai phần dễ đọc: một filter giới hạn tài nguyên và một filter kiểm tra class.

```java
ObjectInputFilter limits = SerializationLimits.FILTER;
ObjectInputFilter classes = MessagePolicy.classFilter();

ObjectInputFilter combined =
        ObjectInputFilter.merge(limits, classes);

ObjectInputFilter strict =
        ObjectInputFilter.rejectUndecidedClass(combined);
```

Filter `strict` sẽ từ chối class không được allowlist chấp nhận, đồng thời vẫn từ chối ngay khi filter giới hạn tài nguyên báo vượt ngưỡng.

### 4.1. Vì sao rejectUndecidedClass hữu ích?

Một filter có thể trả `UNDECIDED` cho class không nằm trong danh sách vì nó không có trách nhiệm quyết định class đó. Nếu không có filter khác từ chối, class có thể tiếp tục được đọc.

Khi policy được thiết kế như allowlist, kết quả chưa quyết định cho một class thường phải được xem là không được phép. `rejectUndecidedClass` biến quy tắc đó thành một wrapper rõ ràng.

Lưu ý: wrapper này chỉ chuyển `UNDECIDED` thành `REJECTED` khi có class để xét. Trường hợp `serialClass()` là null vẫn có thể giữ trạng thái `UNDECIDED` để các filter khác đánh giá chỉ số tài nguyên.

## 5. Dùng pattern filter từ cấu hình

Ngoài viết lambda, Java cung cấp `ObjectInputFilter.Config.createFilter(String pattern)` để tạo filter từ chuỗi pattern. Cách này hữu ích khi muốn cấu hình policy mà không viết class Java riêng.

Ví dụ:

```java
ObjectInputFilter filter = ObjectInputFilter.Config.createFilter(
        "maxdepth=20;"
      + "maxrefs=10000;"
      + "maxbytes=1048576;"
      + "maxarray=100000;"
      + "!com.example.dto.LegacyPayload;"
      + "com.example.dto.**;"
      + "java.lang.String;"
      + "!*"
);
```

Một số thành phần của pattern:

| Pattern | Ý nghĩa |
|---|---|
| `maxdepth=20` | Từ chối khi depth vượt 20 |
| `maxrefs=10000` | Từ chối khi references vượt 10.000 |
| `maxbytes=1048576` | Từ chối khi stream bytes vượt 1 MiB |
| `maxarray=100000` | Từ chối mảng có độ dài vượt 100.000 |
| `com.example.dto.*` | Match class trực tiếp trong package đó |
| `com.example.dto.**` | Match class trong package và các subpackage |
| `!com.example.dto.LegacyPayload` | Từ chối class được chỉ định |
| `!*` | Từ chối class không khớp pattern cho phép trước đó |

Các pattern class được xét theo thứ tự; pattern khớp đầu tiên quyết định trạng thái cho class. Vì vậy, nếu cần từ chối một class nằm trong package được cho phép, đặt pattern từ chối cụ thể trước pattern package rộng.

### 5.1. Pattern filter không thay thế kiểm tra cấu trúc nghiệp vụ

Pattern filter có thể kiểm soát class và một số giới hạn tổng quát, nhưng policy nghiệp vụ phức tạp thường cần filter tùy chỉnh. Ví dụ, cùng một class DTO có thể hợp lệ ở một loại request nhưng không hợp lệ ở một loại request khác.

Ngoài ra, package pattern rộng có thể vô tình cho phép class mới được thêm vào package trong tương lai. Với dữ liệu không tin cậy, allowlist theo class cụ thể thường dễ audit hơn.

### 5.2. Lỗi cấu hình pattern

`createFilter` phân tích chuỗi pattern và có thể ném `IllegalArgumentException` nếu cấu hình sai. Nên tạo filter khi ứng dụng khởi động để phát hiện lỗi cấu hình sớm, thay vì đợi request đầu tiên mới phát hiện.

Không nên âm thầm thay filter lỗi bằng một policy cho phép tất cả class. Nếu cấu hình bảo mật không hợp lệ, ứng dụng nên báo lỗi cấu hình và không khởi động luồng deserialize liên quan.

## 6. Gắn filter vào ObjectInputStream

Filter riêng cho stream được đặt bằng `ObjectInputStream.setObjectInputFilter(filter)`. Hãy đặt filter trước lần gọi `readObject()` đầu tiên.

```java
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.ObjectInputFilter;
import java.io.ObjectInputStream;

static Object readMessage(byte[] serialized) throws IOException, ClassNotFoundException {
    try (ObjectInputStream input =
                 new ObjectInputStream(new ByteArrayInputStream(serialized))) {

        input.setObjectInputFilter(MessagePolicy.strictFilter());

        return input.readObject();
    }
}
```

Filter được áp dụng trong quá trình đọc object graph. Nếu filter từ chối, thao tác giải tuần tự hóa dừng và thường ném `InvalidClassException` với thông tin filter status.

Không đợi deserialize xong mới đặt filter. Khi object graph đã được dựng lên, việc đặt filter muộn không thể bảo vệ các bước đọc đã xảy ra.

### 6.1. Kiểm tra filter đã được gắn

Có thể đọc filter hiện tại của stream bằng `getObjectInputFilter()`:

```java
ObjectInputFilter current = input.getObjectInputFilter();
System.out.println(current);
```

Điều này hữu ích trong chẩn đoán cấu hình. Không log nội dung nhạy cảm của object graph chỉ để xác nhận filter đã được cài.

### 6.2. Filter toàn JVM

Có thể cấu hình filter toàn cục bằng `ObjectInputFilter.Config.setSerialFilter(filter)` hoặc thuộc tính JVM `jdk.serialFilter` khi khởi động.

Filter toàn cục tạo lớp bảo vệ nền cho các `ObjectInputStream` trong tiến trình. Nó nên được cấu hình sớm, thường ở bootstrap của ứng dụng, vì API toàn cục có quy tắc thiết lập một lần.

Một filter toàn cục quá chặt có thể làm hỏng các luồng serialization hợp lệ của thư viện khác. Hãy thống kê các use case trước khi triển khai và kết hợp với policy theo từng luồng khi cần.

## 7. Kiểm thử từ chối class không được phép

Một policy chỉ có giá trị khi kiểm thử chứng minh rằng nó từ chối dữ liệu ngoài allowlist.

Ví dụ một class không được phép:

```java
import java.io.Serializable;

final class UnexpectedPayload implements Serializable {
    private static final long serialVersionUID = 1L;

    private final String value = "unexpected";
}
```

Hàm serialize phục vụ kiểm thử:

```java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.ObjectOutputStream;

static byte[] serialize(Object value) throws IOException {
    try (ByteArrayOutputStream bytes = new ByteArrayOutputStream();
         ObjectOutputStream output = new ObjectOutputStream(bytes)) {
        output.writeObject(value);
        output.flush();
        return bytes.toByteArray();
    }
}
```

Kiểm thử từ chối:

```java
import java.io.ByteArrayInputStream;
import java.io.InvalidClassException;
import java.io.ObjectInputStream;

byte[] data = serialize(new UnexpectedPayload());

try (ObjectInputStream input =
             new ObjectInputStream(new ByteArrayInputStream(data))) {

    input.setObjectInputFilter(MessagePolicy.strictFilter());

    try {
        input.readObject();
        throw new AssertionError("Class ngoài allowlist phải bị từ chối");
    } catch (InvalidClassException expected) {
        System.out.println("Rejected as expected: " + expected.getMessage());
    }
}
```

Khi class không được allowlist chấp nhận, filter trả `REJECTED` và `readObject()` không trả về object đó. Đây là một kiểm thử âm (*negative test*): xác nhận dữ liệu không hợp lệ bị chặn.

Không chỉ kiểm thử bằng cách gọi trực tiếp filter lambda. Hãy kiểm thử qua `ObjectInputStream` thực tế để xác nhận filter được gắn đúng thời điểm và exception được phát sinh như mong đợi.


## 8. Kiểm thử giới hạn tài nguyên quá mức

Bên cạnh class lạ, cần kiểm thử object graph vượt giới hạn. Các test nên bao phủ từng chỉ số thay vì chỉ một trường hợp tổng hợp.

| Tình huống | Dữ liệu kiểm thử | Kỳ vọng |
|---|---|---|
| Depth quá lớn | Object lồng nhiều tầng | `REJECTED` khi vượt `MAX_DEPTH` |
| References quá lớn | Đồ thị có nhiều object | `REJECTED` khi vượt `MAX_REFERENCES` |
| Array quá lớn | Mảng dài hơn ngưỡng | `REJECTED` khi vượt `MAX_ARRAY_LENGTH` |
| Stream quá lớn | Payload serialization vượt byte budget | `REJECTED` khi vượt `MAX_STREAM_BYTES` |
| Class ngoài allowlist | Object có class không được phép | `REJECTED` |
| Payload hợp lệ trong giới hạn | DTO được cho phép và đúng kích thước | Được deserialize |

### 8.1. Kiểm thử mảng vượt giới hạn

Giả sử filter cho phép mảng primitive nhưng giới hạn độ dài ở 256:

```java
static ObjectInputFilter arrayLimit(long maxLength) {
    return info -> {
        if (info.arrayLength() > maxLength) {
            return ObjectInputFilter.Status.REJECTED;
        }

        return ObjectInputFilter.Status.UNDECIDED;
    };
}
```

Dữ liệu kiểm thử:

```java
byte[] serialized = serialize(new byte[1024]);

try (ObjectInputStream input =
             new ObjectInputStream(new ByteArrayInputStream(serialized))) {

    input.setObjectInputFilter(arrayLimit(256));

    try {
        input.readObject();
        throw new AssertionError("Mảng quá lớn phải bị từ chối");
    } catch (InvalidClassException expected) {
        System.out.println("Array limit enforced");
    }
}
```

Filter sẽ được gọi khi mảng được đọc và có thể từ chối dựa trên `arrayLength()` trước khi ứng dụng sử dụng mảng đó.

### 8.2. Kiểm thử depth và references

Có thể tạo các class test có liên kết lồng nhau hoặc nhiều node tham chiếu để tạo object graph vượt ngưỡng. Ví dụ cấu trúc node:

```java
final class Node implements Serializable {
    private static final long serialVersionUID = 1L;

    Node next;
    String value;
}
```

Tạo chuỗi node dài hơn giới hạn depth rồi serialize để làm fixture cho test. Với references, tạo object graph gồm nhiều node hoặc nhiều phần tử tham chiếu riêng biệt.

Không cần hard-code một payload nguy hiểm trong test. Chỉ cần fixture xác định, có kích thước hữu hạn và chứng minh filter từ chối đúng ngưỡng.

### 8.3. Kiểm thử byte budget

`streamBytes()` tăng khi `ObjectInputStream` tiêu thụ dữ liệu. Một payload lớn hơn budget phải bị từ chối khi filter được gọi và số byte đã đọc vượt ngưỡng.

Hãy test cả trường hợp:

- Payload hợp lệ nhỏ hơn ngưỡng.
- Payload đúng bằng ngưỡng (nếu policy cho phép bằng ngưỡng).
- Payload vượt ngưỡng một lượng nhỏ.
- Payload chứa nhiều object nhỏ nhưng tổng byte lớn.

Giới hạn byte không thay thế giới hạn mảng hoặc depth; các test cần kiểm tra từng chiều riêng.

## 9. Kiểm thử dương và âm trong cùng bộ test

Một bộ test tốt cần xác nhận cả dữ liệu được phép lẫn dữ liệu bị từ chối. Nếu chỉ test từ chối, policy có thể quá chặt đến mức không nhận cả payload hợp lệ. Nếu chỉ test chấp nhận, policy có thể bỏ lọt class ngoài allowlist.

Ma trận test đề xuất:

| Nhóm test | Dữ liệu | Kết quả mong đợi |
|---|---|---|
| Positive: DTO hợp lệ | `Message` với `String` | Deserialize thành công |
| Negative: class lạ | `UnexpectedPayload` | `InvalidClassException` |
| Negative: array lớn | `byte[]` vượt ngưỡng | `InvalidClassException` |
| Negative: depth lớn | Chuỗi `Node` lồng quá sâu | `InvalidClassException` |
| Negative: references nhiều | Đồ thị nhiều object | `InvalidClassException` |
| Negative: stream lớn | Byte stream vượt budget | `InvalidClassException` |
| Boundary: bằng ngưỡng | Dữ liệu đúng giới hạn | Theo quy tắc `>` hoặc `>=` đã chọn |
| Regression | Payload hợp lệ cũ | Tiếp tục deserialize được |

### 9.1. Đảm bảo test chứng minh filter đã thực sự chạy

Một negative test có thể thất bại vì payload hỏng, class không có mặt trên classpath hoặc `serialVersionUID` không khớp. Những trường hợp đó không chứng minh filter từ chối.

Để test có ý nghĩa:

1. Tạo payload hợp lệ bằng cùng class fixture trong test.
2. Xác nhận payload có thể deserialize nếu dùng filter cho phép.
3. Dùng policy hạn chế để đọc chính payload đó.
4. Xác nhận thao tác thất bại vì filter từ chối.
5. Giữ một positive test để bảo đảm policy cho phép đúng class cần thiết.

### 9.2. Không dùng dữ liệu production nhạy cảm làm fixture

Test filter nên dùng class và dữ liệu giả lập, có thể tái tạo. Không đưa session token, thông tin cá nhân hoặc payload khách hàng thật vào test fixture hoặc log lỗi.

## 10. Chính sách theo ngữ cảnh với JEP 415

Một ứng dụng lớn có thể có nhiều luồng deserialize với mục đích khác nhau:

- Đọc message từ một giao thức nội bộ.
- Nạp cache đã lưu.
- Khôi phục trạng thái tác vụ.
- Đọc file cấu hình tương thích cũ.
- Nhận payload từ một thành phần plugin.

Một filter toàn cục duy nhất có thể quá rộng cho một số luồng và quá chặt cho luồng khác. Java 17 bổ sung **serialization filter factory** qua JEP 415 để chọn hoặc kết hợp filter cho từng `ObjectInputStream`.

Factory được cấu hình ở cấp JVM thông qua `ObjectInputFilter.Config.setSerialFilterFactory(...)`. Nó nhận filter hiện tại và filter được yêu cầu, sau đó trả về filter sẽ được sử dụng.

### 10.1. Factory nhận hai filter

Chữ ký factory sử dụng `BinaryOperator<ObjectInputFilter>`:

```java
ObjectInputFilter.Config.setSerialFilterFactory(
        (currentFilter, requestedFilter) -> {
            // Chọn hoặc kết hợp filter theo chính sách ứng dụng.
            return requestedFilter;
        }
);
```

Ý nghĩa khái quát:

- `currentFilter` là filter hiện đang được áp dụng cho stream; khi tạo stream mới, giá trị này có thể là null.
- `requestedFilter` là filter được yêu cầu ở điểm gọi factory, có thể đến từ cấu hình toàn cục hoặc thao tác đặt filter cho stream.
- Giá trị trả về là filter được áp dụng sau khi factory xử lý.

Factory được gọi khi `ObjectInputStream` được tạo và khi stream yêu cầu thay đổi filter bằng `setObjectInputFilter`. Vì factory có thể quyết định kết hợp hoặc thay thế filter, nó là điểm tập trung để áp dụng chính sách.

### 10.2. Kết hợp filter mà không làm mất chính sách nền

Nếu ứng dụng cần giữ cả filter hiện tại và filter được yêu cầu, dùng `ObjectInputFilter.merge`:

```java
ObjectInputFilter.Config.setSerialFilterFactory(
        (currentFilter, requestedFilter) -> {
            if (currentFilter == null) {
                return requestedFilter;
            }

            if (requestedFilter == null) {
                return currentFilter;
            }

            return ObjectInputFilter.merge(
                    currentFilter,
                    requestedFilter
            );
        }
);
```

Khi merge, bất kỳ filter nào trả `REJECTED` đều làm kết quả bị từ chối. Một filter không thể ghi đè quyết định từ chối của filter còn lại bằng cách trả `ALLOWED`.

Đây là đặc tính quan trọng khi kết hợp chính sách nền toàn ứng dụng với policy riêng của từng luồng.

### 10.3. Chọn filter theo ngữ cảnh ứng dụng

JEP 415 cho phép factory chọn policy dựa trên ngữ cảnh mà ứng dụng cung cấp. Ngữ cảnh có thể là:

- Loại thao tác đang thực hiện.
- Module hoặc class loader khởi tạo stream.
- Thành phần ứng dụng hoặc endpoint.
- Policy được gắn vào request hoặc thread trước khi tạo stream.
- Filter riêng do caller yêu cầu.

Ví dụ minh họa dùng `ThreadLocal` để chuyển policy của thao tác hiện tại đến factory. Factory phải được cài đặt một lần ở giai đoạn khởi động ứng dụng:

```java
import java.io.ObjectInputFilter;

final class ContextFilters {
    private static final ThreadLocal<ObjectInputFilter> CONTEXT =
            new ThreadLocal<>();

    static ObjectInputFilter merge(
            ObjectInputFilter first,
            ObjectInputFilter second) {

        if (first == null) {
            return second;
        }

        if (second == null) {
            return first;
        }

        return ObjectInputFilter.merge(first, second);
    }

    static void installFactory() {
        ObjectInputFilter.Config.setSerialFilterFactory(
                (current, requested) -> {
                    ObjectInputFilter context = CONTEXT.get();

                    ObjectInputFilter combined =
                            merge(current, requested);

                    return merge(combined, context);
                }
        );
    }

    static ObjectInputFilter currentContext() {
        return CONTEXT.get();
    }

    static void setContext(ObjectInputFilter filter) {
        CONTEXT.set(filter);
    }

    static void clearContext() {
        CONTEXT.remove();
    }
}
```

Khi xử lý một request, ứng dụng đặt policy trước khi tạo `ObjectInputStream`:

```java
ObjectInputFilter previous = ContextFilters.currentContext();
ContextFilters.setContext(policyForMessageEndpoint());

try (ObjectInputStream input =
             new ObjectInputStream(sourceStream)) {

    return input.readObject();
} finally {
    if (previous == null) {
        ContextFilters.clearContext();
    } else {
        ContextFilters.setContext(previous);
    }
}
```

Factory lấy policy khi stream được tạo, rồi gắn filter tương ứng với stream đó. Khôi phục hoặc xóa context trong `finally` để tránh policy của request trước rò sang request tiếp theo trên cùng thread.

Ví dụ này minh họa cơ chế truyền ngữ cảnh. Trong ứng dụng bất đồng bộ, nơi stream có thể được tạo trên thread khác, nên truyền policy tường minh qua context của tác vụ thay vì giả định thread-local tự đi theo tác vụ.

### 10.4. Factory là cấu hình cấp tiến trình

`setSerialFilterFactory` là cấu hình toàn JVM và chỉ được thiết lập một lần. Vì vậy:

- Cài đặt ở bootstrap của ứng dụng trước khi tạo các stream.
- Không để từng thư viện độc lập tự thay factory.
- Nếu nhiều thành phần cần policy, factory trung tâm phải điều phối chúng.
- Không ghi đè filter nền đã được cấu hình mà không có chủ ý.
- Kiểm thử factory trong môi trường khởi động giống production.

Nếu factory đã được thiết lập bởi container hoặc thành phần khác, lời gọi thiết lập lại có thể thất bại. Đây là vấn đề cấu hình ứng dụng, không nên giải quyết bằng cách âm thầm bỏ filter.


## 11. Global filter, stream filter và filter factory

Ba cơ chế có vai trò khác nhau:

| Cơ chế | Phạm vi | Mục đích |
|---|---|---|
| Global serial filter | Toàn JVM | Chính sách nền cho các stream |
| Stream-specific filter | Một `ObjectInputStream` | Giới hạn riêng cho luồng dữ liệu |
| Filter factory | Toàn JVM, được gọi theo từng stream | Chọn/kết hợp filter theo ngữ cảnh |

Có thể cấu hình global filter bằng thuộc tính JVM `jdk.serialFilter` hoặc API `Config.setSerialFilter`. Stream-specific filter được đặt qua `setObjectInputFilter`. Factory quyết định filter cuối cùng dựa trên filter hiện tại, filter được yêu cầu và context ứng dụng.

### 11.1. Không để stream policy làm yếu global policy

Nếu global filter từ chối một class, stream-specific filter không nên được phép biến quyết định đó thành chấp nhận. Khi cần kết hợp, dùng `ObjectInputFilter.merge` để bảo đảm một quyết định `REJECTED` được giữ lại.

Một policy riêng có thể bổ sung giới hạn chặt hơn cho một endpoint. Nó không nên mở rộng quyền theo cách vô tình bỏ qua các giới hạn nền của tiến trình.

### 11.2. Chọn chính sách theo mục đích dữ liệu

Ví dụ:

| Ngữ cảnh | Policy gợi ý |
|---|---|
| Message nhỏ từ endpoint nội bộ | Allowlist DTO cụ thể, depth và bytes thấp |
| Cache object có cấu trúc đã biết | Allowlist class cache, giới hạn references và bytes theo kích thước cache |
| File trạng thái lớn | Allowlist riêng, giới hạn bytes/array phù hợp với file format |
| Dữ liệu từ plugin | Policy riêng theo plugin được tin cậy, giới hạn chặt và kiểm soát class loader |
| Dữ liệu không tin cậy từ internet | Tránh native Java serialization nếu có thể; nếu bắt buộc, allowlist rất hẹp và nhiều giới hạn |

Không lấy policy của một endpoint rồi dùng chung cho mọi loại dữ liệu chỉ vì các luồng đều gọi `readObject()`.

## 12. Phân tích lỗi khi filter từ chối

Khi filter trả `REJECTED`, `ObjectInputStream` thường ném `InvalidClassException`. Exception này có thể xuất hiện khi class bị từ chối hoặc một giới hạn filter bị vượt.

Ví dụ xử lý:

```java
try (ObjectInputStream input =
             new ObjectInputStream(sourceStream)) {

    input.setObjectInputFilter(policy);

    Object value = input.readObject();
    handle(value);

} catch (InvalidClassException rejected) {
    logger.warn("Serialized input rejected by filter", rejected);
}
```

Trong log vận hành, nên ghi:

- Endpoint hoặc loại tác vụ.
- Policy/version được sử dụng.
- Nhóm nguyên nhân nếu có thể xác định: class, depth, references, array hay bytes.
- Request correlation ID không nhạy cảm.
- Không ghi toàn bộ payload hoặc dữ liệu bí mật.

Nếu cần phân biệt lý do từ chối, filter tùy chỉnh có thể ghi metric hoặc sự kiện khi phát hiện ngưỡng/class không hợp lệ. Hãy tránh log một dòng cho mọi lần filter được gọi vì filter có thể được gọi rất nhiều lần trong một object graph.

### 12.1. Không coi mọi InvalidClassException là filter rejection

`InvalidClassException` còn có thể xuất hiện do các vấn đề serialization khác, ví dụ class không tương thích hoặc serial version không khớp. Khi điều tra, cần xem thông điệp, nguyên nhân và vị trí phát sinh thay vì quy mọi lỗi thành filter.

### 12.2. Không tiếp tục xử lý object sau khi bị từ chối

Khi `readObject()` thất bại do filter, không có object hợp lệ để chuyển sang tầng nghiệp vụ. Hãy kết thúc thao tác, đóng stream và trả lỗi phù hợp cho caller.

Không bắt `InvalidClassException` rồi trả một object mặc định mà không ghi nhận lý do; cách đó có thể che giấu việc dữ liệu đầu vào bị tấn công hoặc bị hỏng.

## 13. Giới hạn và nguyên tắc bảo mật

Serialization filter giảm rủi ro nhưng không phải giải pháp bảo mật duy nhất.

### 13.1. Ưu tiên allowlist thay cho denylist

Denylist cần biết trước mọi class không an toàn. Allowlist chỉ cho phép các class mà giao thức cần, nên dễ xem xét và ít bị bất ngờ khi dependency bổ sung class mới.

Không cho phép rộng các package như toàn bộ `java.util.*` chỉ để hỗ trợ collection nếu payload không thực sự cần chúng. Mỗi class được thêm vào allowlist cần có lý do.

### 13.2. Không deserialize dữ liệu không tin cậy nếu có lựa chọn tốt hơn

Native Java serialization có lịch sử nhiều vấn đề bảo mật liên quan đến gadget chain và side effect trong quá trình khôi phục object. Filter là biện pháp giảm thiểu, nhưng không biến một hệ sinh thái class bất kỳ thành an toàn.

Với giao tiếp bên ngoài, cân nhắc JSON với schema/validation, Protocol Buffers hoặc định dạng dữ liệu có parser được thiết kế cho hợp đồng rõ ràng. Chọn định dạng phù hợp với yêu cầu tương thích, hiệu năng và bảo mật.

### 13.3. Filter không thay thế validation nghiệp vụ

Ngay cả object graph chỉ chứa class được phép vẫn có thể mang giá trị không hợp lệ:

- Số tiền âm hoặc vượt giới hạn.
- Chuỗi quá dài theo quy tắc nghiệp vụ.
- Trạng thái không hợp lệ.
- Tham chiếu logic không tồn tại.
- Tổ hợp field không thỏa invariant.

Sau khi deserialize, vẫn cần kiểm tra dữ liệu theo schema và quy tắc nghiệp vụ trước khi sử dụng.

### 13.4. Không nhầm filter với sandbox

`ObjectInputFilter` quyết định việc chấp nhận object/class và các chỉ số serialization. Nó không sandbox code, không giới hạn mọi hành vi của method được gọi sau deserialize, và không thay thế phân quyền hệ điều hành hoặc cô lập tiến trình.

## 14. Quy trình xây dựng và kiểm thử policy

Một quy trình thực tế có thể gồm:

1. **Liệt kê payload hợp lệ:** xác định class, mảng và cấu trúc object graph mà chức năng thật sự cần.
2. **Xây allowlist:** cho phép class cụ thể, tránh package wildcard rộng nếu không cần.
3. **Đặt resource budget:** chọn depth, references, array length và stream bytes từ dữ liệu thực tế.
4. **Kết hợp policy:** dùng `merge` cho giới hạn tài nguyên và kiểm tra class; dùng `rejectUndecidedClass` cho allowlist nghiêm ngặt.
5. **Gắn filter trước readObject:** đảm bảo không có object nào được đọc trước khi policy áp dụng.
6. **Kiểm thử positive:** payload hợp lệ vẫn đọc được.
7. **Kiểm thử negative:** class lạ và từng giới hạn quá mức đều bị từ chối.
8. **Kiểm thử boundary:** giá trị ngay dưới, bằng và vượt ngưỡng.
9. **Chọn policy theo ngữ cảnh:** dùng filter factory nếu các loại stream cần quyền khác nhau.
10. **Theo dõi vận hành:** đếm số lần từ chối theo policy và nguyên nhân mà không log payload nhạy cảm.

## 15. Ví dụ tổng hợp: policy nghiêm ngặt cho Message

Ví dụ sau kết hợp allowlist, giới hạn tài nguyên và từ chối class chưa được quyết định:

```java
import java.io.ObjectInputFilter;
import java.util.Set;

final class MessagePolicy {

    private static final long MAX_DEPTH = 10;
    private static final long MAX_REFERENCES = 100;
    private static final long MAX_ARRAY_LENGTH = 256;
    private static final long MAX_STREAM_BYTES = 64 * 1024;

    private static final Set<Class<?>> ALLOWED =
            Set.of(Message.class, String.class);

    private static ObjectInputFilter limits() {
        return info -> {
            if (info.depth() > MAX_DEPTH
                    || info.references() > MAX_REFERENCES
                    || info.arrayLength() > MAX_ARRAY_LENGTH
                    || info.streamBytes() > MAX_STREAM_BYTES) {
                return ObjectInputFilter.Status.REJECTED;
            }

            return ObjectInputFilter.Status.UNDECIDED;
        };
    }

    private static ObjectInputFilter classes() {
        return info -> {
            Class<?> type = info.serialClass();

            if (type == null) {
                return ObjectInputFilter.Status.UNDECIDED;
            }

            if (ALLOWED.contains(type)) {
                return ObjectInputFilter.Status.ALLOWED;
            }

            return ObjectInputFilter.Status.UNDECIDED;
        };
    }

    static ObjectInputFilter strictFilter() {
        ObjectInputFilter combined =
                ObjectInputFilter.merge(limits(), classes());

        return ObjectInputFilter.rejectUndecidedClass(combined);
    }
}
```

Sử dụng:

```java
try (ObjectInputStream input =
             new ObjectInputStream(sourceStream)) {

    input.setObjectInputFilter(MessagePolicy.strictFilter());

    Object value = input.readObject();

    if (!(value instanceof Message message)) {
        throw new InvalidObjectException("Expected Message");
    }

    handleMessage(message);
}
```

Filter kiểm tra class và tài nguyên trong lúc dựng object graph. Kiểm tra kiểu kết quả sau `readObject()` là lớp xác nhận bổ sung cho hợp đồng endpoint. Trong một hệ thống thực tế, nên tách class policy, resource budget và xử lý lỗi thành thành phần có thể cấu hình/test độc lập.

## 16. Những lỗi thường gặp

### Lỗi 1. Chỉ kiểm tra class mà không giới hạn tài nguyên

Allowlist ngăn class ngoài danh sách nhưng không tự giới hạn depth, references, array hoặc bytes. Thêm các ngưỡng phù hợp.

### Lỗi 2. Chỉ giới hạn bytes

Payload nhỏ vẫn có thể chứa object graph sâu hoặc nhiều tham chiếu. Dùng nhiều chỉ số cùng lúc.

### Lỗi 3. Cho phép tất cả khi filter trả UNDECIDED

`UNDECIDED` không phải xác nhận an toàn. Với allowlist nghiêm ngặt, dùng `rejectUndecidedClass` hoặc trả `REJECTED` rõ ràng cho class ngoài danh sách.

### Lỗi 4. Chỉ test payload hợp lệ

Cần test class lạ, array lớn, depth, references và stream bytes vượt ngưỡng. Nếu không, không chứng minh được filter từ chối đúng.

### Lỗi 5. Cài filter sau readObject

Filter phải được gắn trước lần đọc object đầu tiên. Cài sau khi dữ liệu đã được deserialize không bảo vệ phần đã đọc.

### Lỗi 6. Pattern package quá rộng

Pattern như `java.util.*` có thể mở rộng bề mặt class được phép ngoài nhu cầu. Ưu tiên class cụ thể hoặc package hẹp.

### Lỗi 7. Để filter riêng ghi đè từ chối của filter nền

Kết hợp filter bằng `ObjectInputFilter.merge` để giữ nguyên mọi quyết định `REJECTED`.

### Lỗi 8. Thiết lập global factory từ nhiều thư viện

Filter factory là cấu hình cấp JVM và chỉ thiết lập một lần. Hãy để ứng dụng hoặc container điều phối tập trung.

### Lỗi 9. Dùng ThreadLocal mà không dọn context

Policy của request trước có thể rò sang request tiếp theo nếu không khôi phục/xóa trong `finally`. Với xử lý bất đồng bộ, truyền context rõ ràng.

### Lỗi 10. Nghĩ filter giới hạn mọi tài nguyên của tiến trình

Filter chỉ cung cấp các chỉ số serialization. Nó không thay thế giới hạn upload, timeout, quota, memory limit hoặc kiểm soát CPU.

### Lỗi 11. Bắt InvalidClassException rồi tiếp tục với dữ liệu mặc định

Việc từ chối là tín hiệu dữ liệu không phù hợp policy. Hãy kết thúc thao tác và xử lý lỗi có chủ đích.

### Lỗi 12. Xem filter là lý do để tiếp tục dùng native serialization cho dữ liệu tùy ý

Filter giảm rủi ro nhưng không loại bỏ mọi rủi ro gadget hoặc side effect. Tránh deserialize dữ liệu không tin cậy nếu có định dạng phù hợp hơn.

## 17. Bài tập tự luyện

### Bài 1. Ý nghĩa của UNDECIDED

Một filter trả `UNDECIDED` cho class không nằm trong allowlist. Có thể kết luận class đó được cho phép không?

**Đáp án:** Không. `UNDECIDED` chỉ có nghĩa filter này chưa quyết định. Với allowlist nghiêm ngặt, dùng `rejectUndecidedClass` hoặc từ chối class ngoài danh sách.

### Bài 2. Chọn giới hạn phù hợp

Một payload có mảng 200.000 phần tử nhưng tổng stream bytes không vượt budget.

**Câu hỏi:** Chỉ dùng `maxbytes` có đủ không?

**Đáp án:** Không. Cần giới hạn `arrayLength()` bằng `maxarray` hoặc filter tùy chỉnh.

### Bài 3. Từ chối class

Một endpoint chỉ nhận `Message` và `String` nhưng nhận được `UnexpectedPayload`.

**Đáp án:** Filter class phải trả `REJECTED` cho class ngoài allowlist; `readObject()` sẽ thất bại, thường bằng `InvalidClassException`.

### Bài 4. Kiểm thử boundary

Nếu policy từ chối khi `arrayLength() > 256`, mảng dài 256 và 257 có kết quả thế nào?

**Đáp án:** Mảng 256 chưa vượt ngưỡng; mảng 257 bị từ chối.

### Bài 5. Vai trò của merge

Một filter giới hạn tài nguyên trả `REJECTED` nhưng filter class trả `ALLOWED`. Kết quả merge là gì?

**Đáp án:** `REJECTED`. Một filter từ chối là đủ để filter kết hợp từ chối.

### Bài 6. Khi nào factory được gọi?

**Đáp án:** Filter factory được gọi khi tạo `ObjectInputStream` và khi `setObjectInputFilter` yêu cầu áp dụng filter cho stream. Factory chọn hoặc kết hợp filter theo ngữ cảnh.

### Bài 7. Vì sao phải cài factory một lần?

**Đáp án:** Đây là cấu hình toàn JVM. Nhiều thư viện tự cài factory sẽ xung đột; ứng dụng nên điều phối một factory tập trung.

### Bài 8. Filter có thay validation nghiệp vụ không?

**Đáp án:** Không. Filter kiểm soát class và một số chỉ số serialization. Sau khi deserialize vẫn cần kiểm tra giá trị và invariant nghiệp vụ.

### Bài 9. Vì sao cần positive test?

**Đáp án:** Negative test chứng minh dữ liệu xấu bị chặn; positive test chứng minh policy vẫn cho phép payload hợp lệ và không gây lỗi chức năng.

### Bài 10. Có thể dùng filter để sandbox mã không tin cậy không?

**Đáp án:** Không. Filter không sandbox code và không thay thế cô lập tiến trình hoặc kiểm soát quyền hệ điều hành.

## 18. Tài liệu tham khảo chính thức

- [JDK 17 API — ObjectInputFilter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputFilter.html): trạng thái ALLOWED/REJECTED/UNDECIDED, FilterInfo, merge và rejectUndecidedClass.
- [JDK 17 API — ObjectInputFilter.Config](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputFilter.Config.html): tạo filter từ pattern, global filter và filter factory.
- [JDK 17 API — ObjectInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputStream.html): gắn filter riêng cho stream và giải tuần tự hóa object.
- [JDK 17 API — InvalidClassException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InvalidClassException.html): exception khi class bị từ chối hoặc không tương thích.
- [OpenJDK JEP 290 — Filter Incoming Serialization Data](https://openjdk.org/jeps/290): serialization filter, class filtering và giới hạn tài nguyên.
- [OpenJDK JEP 415 — Context-Specific Deserialization Filters](https://openjdk.org/jeps/415): filter factory theo ngữ cảnh được bổ sung trong Java 17.

**Ghi nhớ:** Dùng `ObjectInputFilter` để kiểm tra class và giới hạn depth, references, array length, stream bytes trong lúc deserialize. Với allowlist nghiêm ngặt, kết hợp `merge` và `rejectUndecidedClass` để giữ quyết định từ chối và loại class chưa được chấp nhận. Java 17 bổ sung filter factory theo JEP 415 để chọn policy theo từng stream. Luôn kiểm thử cả payload hợp lệ, class bị từ chối, từng ngưỡng tài nguyên và các giá trị biên; filter là lớp phòng vệ bổ sung, không phải sandbox hay bảo đảm an toàn cho mọi dữ liệu serialization không tin cậy.
