# Nguy cơ khi đọc dữ liệu đối tượng không đáng tin cậy trong Java 17

> **Chủ đề:** Java 17  
> **Chương:** Lọc giải tuần tự hóa  
> **Phạm vi:** Java Object Serialization và cơ chế lọc đối tượng của JPMS/JDK hiện hành. Nội dung tập trung vào các API còn dùng được trong Java 17, đặc biệt là `ObjectInputFilter` (JEP 290) và `ObjectInputFilter.Config` filter factory (JEP 415).

## 1. Vì sao đọc object stream có thể nguy hiểm?

Java hỗ trợ chuyển một object graph thành chuỗi byte bằng **serialization** và dựng lại object graph từ chuỗi byte bằng **deserialization**. API quen thuộc gồm:

- `ObjectOutputStream` để ghi đối tượng.
- `ObjectInputStream` để đọc và dựng lại đối tượng.
- `Serializable` để đánh dấu class có thể tham gia cơ chế serialization mặc định.
- `Externalizable` để class tự kiểm soát cách ghi và đọc dữ liệu.

Với dữ liệu do chính ứng dụng tạo ra, lưu trữ trong vùng tin cậy và được bảo vệ phù hợp, serialization có thể phục vụ một số nhu cầu tương thích. Nhưng khi chương trình đọc object stream do người dùng, mạng, file tải về, message queue hoặc hệ thống bên ngoài cung cấp, dữ liệu đó có thể được thiết kế có chủ đích để kích hoạt hành vi nguy hiểm.

**Không nên coi việc gọi `readObject()` là một thao tác parse dữ liệu thụ động.** Trong quá trình dựng object graph, Java có thể khởi tạo nhiều class và gọi các callback serialization do class định nghĩa. Nếu class phù hợp có mặt trên classpath, một object graph được chế tạo có thể kích hoạt chuỗi hành vi không mong muốn.

Quy tắc an toàn quan trọng nhất:

> Không deserialize dữ liệu Java native serialization từ nguồn không đáng tin cậy. Nếu một hệ thống cũ bắt buộc phải nhận loại dữ liệu này, hãy áp dụng allowlist rất hẹp, giới hạn kích thước object graph, xác thực dữ liệu và kiểm soát dependency.

Object filter làm giảm rủi ro, nhưng không biến một object stream tùy ý thành dữ liệu an toàn.

## 2. Những nhóm rủi ro chính

### 2.1. Thực thi hành vi thông qua gadget chain

Một class có thể định nghĩa các callback được gọi trong quá trình deserialization, chẳng hạn:

- `readObject`: đọc và khôi phục trạng thái của object.
- `readExternal`: logic đọc do class `Externalizable` triển khai.
- `readResolve`: thay object vừa deserialize bằng một object khác.
- Các phương thức/cơ chế khác được kích hoạt gián tiếp bởi callback trên hoặc bởi thao tác sử dụng object sau khi deserialize.

Một **gadget** là class có hành vi hữu ích cho một chuỗi khai thác. Một **gadget chain** kết hợp nhiều class để khi object graph được dựng lại hoặc được sử dụng, các callback dẫn tới hành động nguy hiểm, ví dụ gọi một sink có thể thực thi lệnh, truy cập tài nguyên hoặc thay đổi trạng thái.

Không phải mọi lần gọi `readObject()` đều tự động thực thi lệnh hệ điều hành. Rủi ro phụ thuộc vào các class có thể được nạp, cách chúng xử lý dữ liệu và những gadget/sink hiện diện trong ứng dụng. Tuy nhiên, chỉ cần một thư viện phụ thuộc có gadget phù hợp cũng có thể làm tăng bề mặt tấn công.

### 2.2. Từ chối dịch vụ (Denial of Service)

Object stream độc hại có thể cố làm ứng dụng tiêu tốn quá nhiều tài nguyên:

- **Object graph quá sâu:** chuỗi tham chiếu lồng nhau có thể gây áp lực lên stack hoặc CPU.
- **Quá nhiều object/reference:** tạo số lượng object rất lớn, làm tăng allocation và garbage collection.
- **Array khổng lồ:** khai báo độ dài mảng rất lớn, gây áp lực bộ nhớ.
- **Stream quá lớn:** truyền một lượng byte vượt mức ứng dụng có thể xử lý.
- **Cấu trúc phức tạp hoặc vòng tham chiếu:** làm tăng chi phí dựng graph và xử lý callback.
- **Callback tốn tài nguyên:** một class được phép deserialize có thể thực hiện tính toán hoặc truy cập tài nguyên đắt đỏ trong callback.

Vì vậy, kiểm tra class được phép thôi chưa đủ. Cần giới hạn độ sâu, số tham chiếu, số byte và độ dài mảng phù hợp với dữ liệu hợp lệ.

### 2.3. Vi phạm bất biến dữ liệu và giả định kiểu

Sau khi deserialize, ứng dụng có thể nhận một object mà trạng thái không đáp ứng quy tắc nghiệp vụ mà code thường kỳ vọng. Ví dụ:

- Số lượng âm hoặc vượt giới hạn.
- Trạng thái enum/flag không phù hợp với quy trình.
- Quan hệ giữa các object không nhất quán.
- Tham chiếu null ở vị trí ứng dụng tưởng là luôn có giá trị.
- Object chứa dữ liệu đã cũ, sai phiên bản hoặc do người gửi cố ý sửa đổi.

Không được xem object đã deserialize là hợp lệ chỉ vì nó có đúng class mong đợi. Cần xác thực kiểu gốc, trường dữ liệu, quan hệ giữa các trường và quyền nghiệp vụ trước khi dùng.

### 2.4. Rủi ro tăng theo dependency

Khả năng khai thác không chỉ đến từ class do ứng dụng tự viết. Các thư viện nằm trên classpath/module path cũng có thể cung cấp callback hoặc gadget. Thêm dependency mới có thể làm thay đổi những class có khả năng tham gia quá trình deserialization.

Vì vậy, kiểm soát phiên bản dependency, loại bỏ thư viện không cần thiết và không mở rộng allowlist theo kiểu toàn bộ package lớn là các biện pháp quan trọng.

## 3. Vì sao deserialize có thể gọi code của class?

Java serialization không chỉ đọc một chuỗi byte thành các trường dữ liệu đơn giản. Nó dựng object graph theo quy tắc của từng class.

### 3.1. Callback serialization

Các class có thể tham gia quá trình này bằng những phương thức đặc biệt:

| Cơ chế | Vai trò |
|---|---|
| `private void readObject(ObjectInputStream in)` | Class tự đọc và khôi phục trạng thái; có thể kiểm tra dữ liệu và gọi logic khác |
| `private void readObjectNoData()` | Xử lý trường hợp class trong hierarchy không có dữ liệu tương ứng trong stream |
| `protected Object readResolve()` | Thay object vừa được khôi phục bằng object khác |
| `void readExternal(ObjectInput in)` | Class `Externalizable` tự đọc dữ liệu |
| `ObjectInputValidation` | Đăng ký kiểm tra sau khi object graph được đọc, trước khi trả kết quả cuối cho caller |

Một callback có thể gọi thêm phương thức khác, xử lý collection, tra cứu tài nguyên hoặc tương tác với dependency. Vì thế, dữ liệu đầu vào có thể tác động đến luồng thực thi thông qua class được deserialize.

Ví dụ callback hợp lệ về mặt kỹ thuật nhưng cần được xem xét cẩn thận:

```java
private void readObject(ObjectInputStream in)
        throws IOException, ClassNotFoundException {
    in.defaultReadObject();

    if (quantity < 0) {
        throw new InvalidObjectException("quantity must be non-negative");
    }
}
```

Đoạn code minh họa việc xác thực trạng thái sau khi đọc. Nó không phải bộ lọc class và không đủ để bảo vệ ứng dụng nếu object graph chứa class nguy hiểm khác.

### 3.2. Constructor thông thường không phải hàng rào bảo vệ chung

Đối với class triển khai `Serializable` theo cơ chế mặc định, constructor của class serializable đó không được gọi như khi tạo object bằng `new`. Java khôi phục trạng thái theo serialization protocol; constructor không serializable đầu tiên trong hierarchy được gọi theo quy tắc của serialization.

Vì vậy, không nên chỉ đặt kiểm tra an toàn trong constructor thông thường rồi cho rằng các kiểm tra đó luôn chạy khi deserialize.

`Externalizable` có quy tắc khác: class cần constructor không tham số công khai để runtime tạo instance, sau đó gọi `readExternal`. Record cũng có quy tắc serialization riêng; canonical constructor của record được gọi khi deserialize record.

Dù dùng loại class nào, ứng dụng vẫn cần kiểm tra object sau khi nhận và trước khi dùng nó cho thao tác nhạy cảm.

### 3.3. Kiểm tra dữ liệu sau khi deserialize

Hãy xác thực ở lớp biên của ứng dụng:

```java
static UserProfile validate(Object value) throws InvalidObjectException {
    if (value == null || value.getClass() != UserProfile.class) {
        throw new InvalidObjectException("Unexpected object type");
    }

    UserProfile profile = (UserProfile) value;
    if (profile.age() < 0 || profile.age() > 130) {
        throw new InvalidObjectException("Invalid age");
    }
    if (profile.username() == null || profile.username().isBlank()) {
        throw new InvalidObjectException("Username is required");
    }
    return profile;
}
```

Đây chỉ là ví dụ kiểm tra kiểu và quy tắc nghiệp vụ. Với hệ thống thực tế, kiểm tra thêm độ dài chuỗi, giới hạn số lượng phần tử, quan hệ giữa các object, trạng thái người dùng và quyền của caller.

## 4. ObjectInputFilter: lọc class và giới hạn object graph

Java 9 bổ sung cơ chế lọc object deserialization theo JEP 290. Trong Java 17, API chính là `java.io.ObjectInputFilter`.

Filter được gọi trong quá trình `ObjectInputStream` đọc object graph để ứng dụng có thể quyết định:

- Class nào được phép xuất hiện.
- Object graph sâu đến mức nào.
- Có bao nhiêu reference được xử lý.
- Stream đã tiêu thụ bao nhiêu byte.
- Mảng được deserialize có độ dài tối đa bao nhiêu.

Đây là lớp bảo vệ quan trọng khi một hệ thống cũ chưa thể bỏ Java native serialization. Filter cần được thiết kế theo **allowlist các kiểu thực sự cần**, kết hợp giới hạn tài nguyên.

### 4.1. ObjectInputFilter.FilterInfo

Filter nhận một đối tượng `FilterInfo` chứa thông tin về quá trình đọc:

| Thuộc tính | Ý nghĩa |
|---|---|
| `serialClass()` | Class đang được kiểm tra; có thể là `null` trong một số lần gọi, ví dụ khi không có class mới để kiểm tra |
| `arrayLength()` | Độ dài mảng đang được kiểm tra; giá trị âm nếu không áp dụng |
| `depth()` | Độ sâu hiện tại của object graph |
| `references()` | Số lượng reference đã được xử lý trong stream |
| `streamBytes()` | Số byte đã tiêu thụ từ stream tại thời điểm kiểm tra |

Filter trả về một trong ba trạng thái:

| Trạng thái | Ý nghĩa |
|---|---|
| `ALLOWED` | Filter này cho phép đối tượng/điều kiện đang xét |
| `REJECTED` | Từ chối; deserialization bị dừng bằng lỗi |
| `UNDECIDED` | Filter không đưa ra quyết định; filter khác hoặc cơ chế mặc định có thể tiếp tục tham gia |

Khi chỉ dùng một filter riêng cho stream, cách dễ kiểm soát là **cho phép class nằm trong allowlist và từ chối class khác**. Không trả `UNDECIDED` cho mọi class lạ rồi nghĩ rằng đã tạo allowlist.

### 4.2. Ví dụ filter theo class và giới hạn tài nguyên

Giả sử ứng dụng chỉ chấp nhận một kiểu DTO đơn giản:

```java
import java.io.Serial;
import java.io.Serializable;

public final class UserSnapshot implements Serializable {
    @Serial
    private static final long serialVersionUID = 1L;

    private final String username;
    private final int score;

    public UserSnapshot(String username, int score) {
        this.username = username;
        this.score = score;
    }

    public String username() {
        return username;
    }

    public int score() {
        return score;
    }
}
```

Hàm đọc:

```java
import java.io.IOException;
import java.io.InvalidObjectException;
import java.io.ObjectInputFilter;
import java.io.ObjectInputStream;
import java.nio.file.Files;
import java.nio.file.Path;

static UserSnapshot readSnapshot(Path path)
        throws IOException, ClassNotFoundException {

    try (ObjectInputStream input =
                 new ObjectInputStream(Files.newInputStream(path))) {

        ObjectInputFilter filter = info -> {
            if (info.depth() > 10
                    || info.references() > 100
                    || info.streamBytes() > 1_000_000
                    || info.arrayLength() > 10_000) {
                return ObjectInputFilter.Status.REJECTED;
            }

            Class<?> type = info.serialClass();
            if (type == null) {
                return ObjectInputFilter.Status.UNDECIDED;
            }

            if (type == UserSnapshot.class || type == String.class) {
                return ObjectInputFilter.Status.ALLOWED;
            }

            return ObjectInputFilter.Status.REJECTED;
        };

        // Cài filter trước khi đọc object.
        input.setObjectInputFilter(filter);

        Object value = input.readObject();
        if (value == null || value.getClass() != UserSnapshot.class) {
            throw new InvalidObjectException("Unexpected root object type");
        }

        UserSnapshot snapshot = (UserSnapshot) value;
        if (snapshot.username() == null || snapshot.username().isBlank()
                || snapshot.score() < 0) {
            throw new InvalidObjectException("Invalid user snapshot");
        }
        return snapshot;
    }
}
```

Điểm cần hiểu:

1. Filter được cài sau khi tạo `ObjectInputStream` nhưng **trước lời gọi `readObject()`**.
2. Các giới hạn graph được kiểm tra trước khi quyết định class.
3. Chỉ class DTO được dự kiến mới được cho phép; class khác bị từ chối.
4. `serialClass()` có thể là `null`, nên không được gọi phương thức trên giá trị đó khi chưa kiểm tra.
5. Sau khi đọc, ứng dụng vẫn xác thực object gốc và dữ liệu nghiệp vụ.

Ví dụ này minh họa allowlist rất nhỏ. Khi DTO thực tế chứa collection, kiểu ngày giờ hoặc kiểu serializable khác, phải bổ sung đúng các class cần thiết sau khi hiểu object graph. Không nên mở rộng thành toàn bộ `java.base` hay toàn bộ package thư viện chỉ để làm lỗi biến mất.

### 4.3. Filter không thay thế xác thực dữ liệu

Filter có thể từ chối class hoặc graph vượt giới hạn. Nó không phải bộ validator cho mọi giá trị field:

- Không kiểm tra một username có hợp lệ theo nghiệp vụ hay không.
- Không kiểm tra người gửi có quyền sửa điểm số hay không.
- Không xác thực chữ ký hoặc nguồn gốc của byte stream.
- Không chứng minh callback trong class được allowlist là vô hại.

Vì thế, filter và validation phải được dùng cùng nhau. Nếu object graph chứa class được cho phép nhưng class đó có callback nguy hiểm, allowlist quá rộng vẫn có thể để lọt hành vi không mong muốn.

## 5. Cấu hình filter bằng pattern

Java 17 hỗ trợ cú pháp pattern để mô tả giới hạn và class được phép/từ chối mà không cần tự viết lambda.

### 5.1. Các giới hạn graph

Các thuộc tính giới hạn chính:

| Pattern | Giới hạn |
|---|---|
| `maxdepth=n` | Độ sâu tối đa của graph |
| `maxrefs=n` | Số reference tối đa |
| `maxbytes=n` | Số byte tối đa được đọc |
| `maxarray=n` | Độ dài mảng tối đa |

Ví dụ:

```text
maxdepth=12;maxrefs=5000;maxbytes=1048576;maxarray=10000
```

Các giá trị trên chỉ là ví dụ. Giới hạn đúng phải được đo từ object graph hợp lệ của ứng dụng, cộng thêm biên an toàn phù hợp. Đặt quá thấp có thể làm dữ liệu hợp lệ bị từ chối; đặt quá cao làm giảm hiệu quả bảo vệ.

### 5.2. Pattern class allowlist và denylist

Pattern class hỗ trợ tên class chính xác và wildcard package:

- `com.acme.dto.UserSnapshot`: một class cụ thể.
- `com.acme.dto.*`: class trực tiếp trong package đó.
- `com.acme.dto.**`: class trong package đó và các package con.
- `!com.acme.internal.**`: từ chối các class thuộc package nội bộ này.
- `!*`: từ chối class không được một pattern trước đó cho phép.

Có thể ghi tên module trước tên class, phân cách bằng dấu `/`, khi muốn giới hạn theo module.

Ví dụ pattern:

```text
maxdepth=12;maxrefs=5000;maxbytes=1048576;maxarray=10000;com.acme.dto.**;java.base/java.util.ArrayList;java.base/java.util.HashMap;!*
```

Đây là ví dụ allowlist: cho phép các DTO thuộc package được chỉ định và hai collection class cụ thể, từ chối class còn lại. Hãy thay bằng các kiểu thực sự cần trong ứng dụng; collection có thể chứa thêm kiểu phần tử hoặc kiểu hỗ trợ khác.

### 5.3. Dùng filter pattern khi khởi động JVM

Có thể đặt system property `jdk.serialFilter` khi chạy ứng dụng:

```bash
java -Djdk.serialFilter="maxdepth=12;maxrefs=5000;maxbytes=1048576;maxarray=10000;com.acme.dto.**;java.base/java.util.ArrayList;!*" -jar app.jar
```

Filter này có phạm vi toàn JVM theo cấu hình serialization filter. Nó phù hợp khi tổ chức muốn đặt chính sách mặc định tập trung cho các luồng deserialization.

Đối với cấu hình triển khai, hãy đặt property trong cấu hình runtime/launcher do tổ chức quản lý. Không nên cho một request từ người dùng tự quyết định system property bảo mật.

### 5.4. Cài global filter bằng API

Có thể cài filter toàn JVM bằng `ObjectInputFilter.Config.setSerialFilter`:

```java
ObjectInputFilter.Config.setSerialFilter(globalFilter);
```

Global filter có tính chất process-wide và chỉ được thiết lập theo quy tắc một lần của API. Hãy cài sớm trong quá trình khởi động ứng dụng, trước khi tạo các luồng deserialize cần chính sách đó. Nếu đã có filter từ cấu hình runtime hoặc code khác, cần thiết kế hợp nhất chính sách thay vì cố ghi đè tùy tiện.

### 5.5. Cài filter riêng cho từng stream

Khi mỗi luồng đọc có nhu cầu khác nhau, dùng:

```java
ObjectInputStream input = new ObjectInputStream(source);
input.setObjectInputFilter(streamFilter);
Object value = input.readObject();
```

Filter riêng phải được cài trước khi đọc object đầu tiên. API này hữu ích để áp dụng allowlist theo giao thức hoặc loại dữ liệu của stream đó.

Không nên đợi đọc object xong mới cài filter: lúc đó việc dựng object graph đã diễn ra.

### 5.6. Thứ tự pattern và nguyên tắc allowlist

Pattern filter được phân tách bằng dấu chấm phẩy. Các giới hạn graph được đánh giá để từ chối graph vượt ngưỡng; với class pattern, thứ tự các pattern có ý nghĩa vì pattern khớp đầu tiên quyết định kết quả cho class đó.

Ví dụ:

```text
maxdepth=10;maxrefs=1000;com.acme.dto.**;!com.acme.dto.internal.**;!*
```

Để tránh vô tình mở rộng quyền:

- Ưu tiên tên class cụ thể nếu số class được phép ít.
- Chỉ dùng wildcard package khi tất cả class trong phạm vi đó thực sự cần được deserialize.
- Đặt các quy tắc từ chối cụ thể trước một quy tắc cho phép rộng có thể khớp chúng.
- Kết thúc bằng `!*` nếu muốn từ chối mọi class chưa được allowlist.
- Kiểm thử bằng object graph hợp lệ và các graph cố tình chứa class ngoài allowlist.

Một pattern không nên được xem là chính sách an toàn nếu chỉ liệt kê vài package rộng mà không biết những class nào trong đó có callback serialization.

## 6. Filter factory trong Java 17 (JEP 415)

Một ứng dụng lớn có thể có nhiều thành phần deserialize dữ liệu với yêu cầu khác nhau: một luồng đọc DTO nội bộ, một luồng đọc message từ hệ thống đối tác, và một luồng tương thích với dữ liệu cũ. Một filter toàn cục duy nhất đôi khi không diễn đạt đủ ngữ cảnh.

Java 17 bổ sung **serialization filter factory** theo JEP 415. Filter factory quyết định filter nào được áp dụng khi một `ObjectInputStream` được tạo hoặc khi filter của stream được yêu cầu cài đặt.

### 6.1. Vai trò của factory

Factory nhận filter hiện tại và filter được yêu cầu, rồi trả về filter cuối cùng được dùng. Điều này cho phép ứng dụng:

- Kết hợp chính sách toàn JVM với chính sách riêng của stream.
- Chọn filter theo context của ứng dụng.
- Ngăn một thành phần hạ mức bảo vệ bằng cách thay thế filter đã có.
- Tạo chính sách khác nhau cho những luồng dữ liệu có giao thức khác nhau.

Factory là cơ chế **chọn và kết hợp filter**, không phải một bộ parser thay thế cho `ObjectInputFilter`.

### 6.2. Cài filter factory

API nằm trong `ObjectInputFilter.Config`:

```java
ObjectInputFilter.Config.setSerialFilterFactory(
        (currentFilter, requestedFilter) -> {
            // Ứng dụng quyết định filter cuối cùng.
            // Ví dụ đơn giản: nếu stream yêu cầu filter riêng,
            // kết hợp nó với chính sách hiện tại theo quy tắc của ứng dụng.
            return requestedFilter != null
                    ? requestedFilter
                    : currentFilter;
        });
```

Đoạn trên chỉ minh họa chữ ký và vị trí cài đặt; **không phải factory an toàn hoàn chỉnh**. Trong ứng dụng thật, không được trả filter mới theo cách làm mất filter global hiện có. Cần kết hợp các filter sao cho một filter từ chối thì kết quả cuối cùng vẫn bị từ chối, đồng thời các giới hạn tài nguyên bắt buộc luôn được áp dụng.

Factory có thể được cấu hình qua system property `jdk.serialFilterFactory` hoặc cài bằng API. Cần thiết lập trong giai đoạn khởi động, trước khi các thành phần tạo `ObjectInputStream`.

### 6.3. Tách filter theo context

Một thiết kế thực tế có thể phân loại luồng theo chức năng:

| Context | Chính sách ví dụ |
|---|---|
| Đọc DTO nội bộ | Allowlist class DTO cụ thể, giới hạn graph chặt |
| Đọc dữ liệu đối tác | Allowlist theo schema/giao thức riêng, giới hạn byte và mảng thấp |
| Đọc archive tương thích cũ | Chỉ chạy trong quy trình cô lập, allowlist phiên bản dữ liệu đã biết |

Không nên chọn filter chỉ dựa vào dữ liệu không đáng tin cậy tự khai báo trong stream. Context phải được xác định từ luồng xử lý đáng tin cậy của ứng dụng, chẳng hạn endpoint hoặc adapter đã cấu hình.

## 7. ObjectInputFilter bảo vệ được gì và không bảo vệ được gì?

Filter là lớp phòng vệ quan trọng, nhưng có phạm vi rõ ràng.

### 7.1. Filter có thể làm gì?

- Từ chối class không thuộc allowlist.
- Từ chối class/array theo điều kiện.
- Từ chối object graph vượt giới hạn độ sâu, số reference, số byte hoặc độ dài mảng.
- Áp dụng chính sách chung hoặc chính sách theo từng stream.
- Cho phép hệ thống giám sát và kiểm soát những loại object đang được deserialize.

### 7.2. Filter không làm gì?

- Không xác thực danh tính người gửi.
- Không kiểm tra chữ ký, MAC hoặc tính toàn vẹn của byte stream.
- Không kiểm tra mọi giá trị field theo quy tắc nghiệp vụ.
- Không bảo đảm class được allowlist không có callback nguy hiểm.
- Không ngăn mọi kiểu tiêu thụ CPU/memory trong callback của class đã được phép.
- Không thay thế giới hạn kích thước ở tầng mạng, HTTP, file upload hoặc message broker.
- Không tự bảo vệ dữ liệu đi qua JSON, XML, YAML hay định dạng khác; các parser đó cần chính sách riêng.

Ví dụ, nếu cho phép một class DTO có `readObject` tự thực hiện truy vấn tốn kém, filter đã cho phép class đó không thể tự biết truy vấn có hợp lý hay không. Hãy giữ callback đơn giản và không thực hiện side effect nhạy cảm trong quá trình khôi phục object.

### 7.3. Filter không phải sandbox

Không nên dựa vào filter để chạy object stream tùy ý của người dùng trong cùng tiến trình với ứng dụng nhạy cảm. Nếu có nhu cầu xử lý dữ liệu legacy không thể tin cậy, cân nhắc cô lập quy trình với quyền hệ điều hành tối thiểu, tài nguyên giới hạn, timeout và giao tiếp qua một schema dữ liệu hẹp.

Các cơ chế quản lý quyền cũ không phải giải pháp thay thế cho việc không deserialize dữ liệu không tin cậy. Hãy dùng ranh giới tiến trình và quyền hệ điều hành phù hợp với môi trường triển khai hiện hành.

## 8. Quy trình xử lý an toàn khi buộc phải giữ Java serialization

Nếu một giao thức legacy buộc phải nhận Java object stream, hãy xây một ranh giới xử lý rõ ràng.

### 8.1. Giới hạn dữ liệu trước khi tạo ObjectInputStream

Object filter có giới hạn `maxbytes`, nhưng tầng nhận dữ liệu cũng cần giới hạn kích thước:

- HTTP endpoint đặt giới hạn request body.
- Upload đặt giới hạn file trước khi lưu hoặc xử lý.
- Message broker đặt giới hạn message và quota theo producer.
- Socket protocol giới hạn frame length trước khi cấp phát buffer.

Không đọc toàn bộ dữ liệu từ mạng vào một mảng byte không giới hạn rồi mới hy vọng filter từ chối kịp.

### 8.2. Xác thực nguồn và tính toàn vẹn khi giao thức yêu cầu

Nếu byte stream được lưu hoặc truyền qua môi trường có thể bị sửa đổi, có thể dùng chữ ký số hoặc MAC theo giao thức để xác thực nguồn/tính toàn vẹn. Khi có thể, xác minh trên frame byte đã được giới hạn kích thước **trước khi** tạo `ObjectInputStream` và deserialize.

Xác thực chữ ký/MAC không thay thế filter. Một nguồn được xác thực vẫn có thể gửi dữ liệu lỗi, dữ liệu quá lớn hoặc dữ liệu từ phiên bản không tương thích; khóa ký cũng có thể bị lộ hoặc nguồn đáng tin cậy bị xâm nhập.

### 8.3. Dùng allowlist nhỏ và giới hạn graph

Chỉ cho phép:

- DTO cụ thể mà giao thức cần.
- Collection cụ thể nếu định dạng thực sự chứa collection.
- Các kiểu hỗ trợ đã được xem xét.

Đặt ngưỡng cho:

- Độ sâu graph.
- Số reference.
- Byte đã đọc.
- Độ dài array.

Các ngưỡng cần được xác định từ dữ liệu hợp lệ thực tế, không lấy tùy tiện một con số lớn.

### 8.4. Xác thực object sau khi đọc

Ngay cả khi filter cho phép class, hãy kiểm tra:

- Kiểu object gốc chính xác.
- Giá trị bắt buộc không null/rỗng.
- Giới hạn chuỗi và collection.
- Giá trị số nằm trong miền hợp lệ.
- Quan hệ giữa các trường và object liên quan.
- Quyền của người gửi đối với hành động mà dữ liệu yêu cầu.

Không gọi thao tác nhạy cảm (ghi database, chuyển tiền, thực thi lệnh, gửi thông báo) chỉ vì object đã deserialize thành công.

### 8.5. Giữ callback serialization đơn giản

Trong các class serializable do ứng dụng kiểm soát:

- Tránh truy cập mạng, file, database hoặc gọi dịch vụ bên ngoài trong `readObject`/`readExternal`.
- Không thực thi lệnh hoặc tạo thread trong callback khôi phục object.
- Chỉ khôi phục dữ liệu cần thiết và kiểm tra bất biến cục bộ.
- Dùng bước validation rõ ràng sau khi graph được dựng xong.
- Hạn chế `Externalizable` vì class tự kiểm soát protocol và cần được xem xét cẩn thận.

### 8.6. Giảm bề mặt gadget

- Loại bỏ dependency không cần thiết.
- Cập nhật thư viện lên bản vá bảo mật được hỗ trợ.
- Tránh classpath chứa những thư viện cũ không còn dùng.
- Không cho phép class theo wildcard quá rộng.
- Ghi nhận và kiểm thử thay đổi allowlist khi thêm dependency.

## 9. Có nên thay Java native serialization bằng định dạng khác?

Đối với dữ liệu đến từ bên ngoài hoặc cần lưu lâu dài, thường nên dùng định dạng dữ liệu có schema hoặc DTO rõ ràng thay vì deserialize object graph tùy ý.

Các lựa chọn phổ biến:

| Định dạng | Đặc điểm | Điều cần kiểm soát |
|---|---|---|
| JSON với DTO/schema | Dễ đọc, phổ biến giữa nhiều ngôn ngữ | Không bật polymorphic typing tùy tiện; giới hạn độ sâu/kích thước; validate schema và field |
| Protocol Buffers | Schema rõ, encoding nhị phân, hỗ trợ nhiều ngôn ngữ | Kiểm soát version/schema, kích thước message và validation nghiệp vụ |
| Avro | Schema-driven, phù hợp pipeline dữ liệu | Quản lý schema evolution và giới hạn tài nguyên parser |
| CBOR | Biểu diễn dữ liệu kiểu JSON ở dạng nhị phân | Dùng parser cấu hình an toàn, giới hạn depth/size và kiểu dữ liệu |
| MessagePack | Encoding nhị phân gọn cho cấu trúc dữ liệu | Không tự động tin dữ liệu; giới hạn độ sâu, số phần tử và kiểu được chấp nhận |

Chuyển sang JSON không tự động giải quyết mọi vấn đề. Một thư viện JSON cho phép chỉ định tên class và khởi tạo kiểu tùy ý (polymorphic deserialization/auto type) vẫn có thể tạo bề mặt gadget tương tự. Hãy ánh xạ vào DTO cụ thể, tắt cơ chế tự khởi tạo class theo dữ liệu đầu vào nếu không cần, và kiểm tra schema.

### 9.1. Ví dụ tư duy DTO thay cho object graph

Thay vì nhận một object graph tùy ý:

```java
Object value = input.readObject();
```

Giao thức dữ liệu có thể định nghĩa một cấu trúc hẹp:

```json
{
  "username": "linh",
  "score": 42
}
```

Sau khi parse, ánh xạ vào DTO đã biết:

```java
record UserSnapshot(String username, int score) { }
```

Ứng dụng chỉ chấp nhận các trường được định nghĩa và validate giá trị trước khi dùng. Ví dụ JSON chỉ minh họa schema dữ liệu; parser thực tế vẫn cần cấu hình giới hạn và validation.

### 9.2. Khi nào giữ native serialization?

Có thể còn hệ thống nội bộ cần tương thích với dữ liệu đã ghi bằng Java serialization. Khi đó:

- Xác định rõ nguồn tạo dữ liệu và ranh giới tin cậy.
- Chỉ đọc từ kho dữ liệu được bảo vệ và có kiểm soát truy cập.
- Có filter toàn cục hoặc filter theo stream với allowlist.
- Có giới hạn tài nguyên và kiểm tra nghiệp vụ sau khi đọc.
- Có kế hoạch thay thế dần nếu dữ liệu cần trao đổi với bên ngoài hoặc lưu trữ lâu dài.

Không nên mở endpoint công khai nhận object stream tùy ý chỉ vì client cũng được viết bằng Java.

## 10. Những giới hạn kỹ thuật cần nhớ khi dùng filter

### 10.1. Filter không kiểm tra mọi giá trị primitive và String

Object filter chủ yếu kiểm tra class/array và thông tin của object graph trong các điểm runtime gọi filter. Nó không phải bộ kiểm tra từng byte hoặc từng field. Các giá trị primitive và instance `String` không được lọc như các object class thông thường.

Vì vậy:

- Không dựa vào allowlist class để giới hạn độ dài một chuỗi.
- Giới hạn tổng byte stream bằng `maxbytes` và giới hạn chuỗi theo nghiệp vụ sau khi đọc.
- Với dữ liệu có nhiều chuỗi, cần tính cả số lượng chuỗi và tổng dung lượng.
- Không coi `serialClass() == null` là bằng chứng dữ liệu an toàn; đó chỉ là tình huống filter không có class mới để quyết định.

### 10.2. Filter không xác minh cấu trúc nghiệp vụ của object graph

Một graph có thể chỉ chứa các class nằm trong allowlist nhưng vẫn sai về logic. Ví dụ, một `ArrayList` được phép có thể chứa số lượng phần tử vượt mức nghiệp vụ, hoặc DTO có trường trạng thái không hợp lệ. Giới hạn graph và validation nghiệp vụ giải quyết hai vấn đề khác nhau.

### 10.3. Filter không phải giới hạn thời gian thực thi

`maxdepth`, `maxrefs`, `maxbytes` và `maxarray` giúp kiểm soát các chỉ số cấu trúc. Chúng không đảm bảo callback của một class được phép sẽ hoàn thành trong thời gian ngắn. Nếu callback thực hiện công việc đắt đỏ, cần thiết kế lại class, giới hạn thời gian ở tầng xử lý và cô lập quy trình khi cần.

### 10.4. serialVersionUID không phải cơ chế bảo mật

`serialVersionUID` hỗ trợ kiểm tra tương thích phiên bản của class trong Java serialization. Nó không xác thực người gửi, không ký dữ liệu và không ngăn gadget chain. Đừng xem việc khai báo một UID cố định là biện pháp bảo vệ deserialization.

### 10.5. transient không phải hàng rào an toàn cho toàn object

`transient` ngăn một field được ghi theo cơ chế serialization mặc định. Nó không làm cho class an toàn để deserialize, không chặn callback và không thay thế filter. Các field khác hoặc logic tùy chỉnh vẫn có thể tạo hành vi nguy hiểm.

## 11. Các lỗi thường gặp và cách xử lý

| Hiểu nhầm hoặc lỗi | Thực tế | Cách xử lý |
|---|---|---|
| Dữ liệu có đuôi .ser nên chắc chắn đáng tin | Phần mở rộng file không xác thực nguồn | Xác định nguồn, xác thực tính toàn vẹn và dùng filter |
| Chỉ cần kiểm tra object gốc sau readObject | Callback của các object bên trong có thể đã chạy | Lọc graph trước khi dựng object, rồi mới validate object gốc |
| Chỉ cần allowlist class | Graph vẫn có thể quá sâu, quá lớn hoặc có quá nhiều reference | Kết hợp class allowlist với các giới hạn graph |
| Cho phép toàn bộ package của thư viện phổ biến | Package có thể chứa nhiều class không cần thiết hoặc gadget | Cho phép class cụ thể, mở rộng có kiểm soát |
| Trả UNDECIDED cho class không biết | Filter không thể hiện chính sách từ chối | Từ chối class không nằm trong allowlist |
| Cài filter sau readObject | Object graph đã được dựng trước khi filter được áp dụng | Cài filter trước lần đọc object đầu tiên |
| Filter sẽ kiểm tra nội dung mọi String | String và primitive không được lọc như class object thông thường | Giới hạn stream bytes và validate độ dài/giá trị sau khi đọc |
| readObject callback luôn chạy constructor của class | Constructor thường của class Serializable không chạy theo cách tạo object bằng new | Không đặt toàn bộ validation trong constructor; kiểm tra trong callback phù hợp và sau deserialize |
| serialVersionUID làm stream an toàn | UID phục vụ tương thích phiên bản | Dùng filter, xác thực nguồn và validation |
| transient loại bỏ rủi ro deserialization | Callback và các field khác vẫn có thể nguy hiểm | Đánh giá cả class và object graph |
| Dùng JSON là tự động an toàn | Polymorphic typing hoặc auto type không kiểm soát vẫn nguy hiểm | Bind vào DTO/schema cụ thể, giới hạn parser và validate |
| Filter cho phép class nghĩa là callback class vô hại | Allowlist chỉ kiểm soát class, không chứng minh hành vi callback an toàn | Review callback và dependency; tránh side effect |

## 12. Ví dụ cài filter bằng pattern trong code

Nếu muốn tạo filter từ chuỗi pattern thay vì tự viết lambda:

```java
import java.io.ObjectInputFilter;

ObjectInputFilter filter = ObjectInputFilter.Config.createFilter(
        "maxdepth=10;maxrefs=1000;maxbytes=1048576;"
        + "maxarray=10000;com.acme.dto.UserSnapshot;!*");
```

Sau đó gắn vào stream:

```java
try (ObjectInputStream input = new ObjectInputStream(source)) {
    input.setObjectInputFilter(filter);
    Object value = input.readObject();
    // Tiếp tục xác thực kiểu và nội dung của value.
}
```

Pattern này chỉ cho phép một class DTO cụ thể và từ chối các class khác, đồng thời áp dụng giới hạn graph. Nếu DTO có các kiểu object khác cần deserialize, phải bổ sung từng class phù hợp vào allowlist.

Một điểm cần nhớ: pattern filter trả `UNDECIDED` nếu không có pattern nào quyết định class. Vì vậy, quy tắc `!*` cuối cùng hữu ích để từ chối class chưa được liệt kê.

## 13. Checklist thiết kế cho luồng nhận dữ liệu

Trước khi triển khai một endpoint hoặc worker đọc Java object stream, hãy trả lời:

1. Nguồn dữ liệu là ai? Có thể bị người ngoài kiểm soát hoặc sửa đổi không?
2. Có thể thay Java native serialization bằng DTO/schema format không?
3. Nếu bắt buộc deserialize, class nào thực sự cần có trong graph?
4. Allowlist có chỉ chứa các class cần thiết và đã được review callback không?
5. Giới hạn bytes, depth, references và array length là bao nhiêu?
6. Filter được cài trước lần đọc đầu tiên ở cấp global, stream hoặc factory nào?
7. Có xác thực tính toàn vẹn/nguồn gốc trước deserialize khi giao thức cần không?
8. Có kiểm tra kiểu gốc và dữ liệu nghiệp vụ sau khi deserialize không?
9. Có giới hạn tài nguyên ở tầng mạng, file, message và tiến trình không?
10. Khi thêm dependency hoặc nâng phiên bản, ai xem lại allowlist và kết quả kiểm thử?

Đây là các quyết định thiết kế cần được ghi trong cấu hình và tài liệu giao thức; không nên để mỗi nơi gọi `readObject()` tự chọn một chính sách khác nhau.

## 14. Bài tập thực hành

### Bài 1 — Nhận diện rủi ro

Một dịch vụ nhận file do người dùng upload rồi chạy:

```java
try (ObjectInputStream in =
        new ObjectInputStream(Files.newInputStream(uploadedFile))) {
    Object data = in.readObject();
}
```

Hãy nêu ít nhất bốn nhóm rủi ro có thể xuất hiện và giải thích vì sao kiểm tra đuôi file không giải quyết được chúng.

**Gợi ý:** Gadget chain/callback, DoS qua graph hoặc array lớn, dữ liệu vi phạm bất biến, class từ dependency. Phần mở rộng file không chứng minh nguồn gốc hay nội dung.

### Bài 2 — Thiết kế allowlist

Một giao thức chỉ cần đọc class `com.acme.dto.UserSnapshot` với một trường chuỗi và một số nguyên. Hãy viết filter:

- Độ sâu tối đa 5.
- Tối đa 100 references.
- Tối đa 64 KiB stream bytes.
- Chỉ cho phép DTO đó và từ chối class còn lại.

**Gợi ý:**

```java
ObjectInputFilter filter = info -> {
    if (info.depth() > 5
            || info.references() > 100
            || info.streamBytes() > 64 * 1024) {
        return ObjectInputFilter.Status.REJECTED;
    }

    Class<?> type = info.serialClass();
    if (type == null) {
        return ObjectInputFilter.Status.UNDECIDED;
    }
    return type == UserSnapshot.class
            ? ObjectInputFilter.Status.ALLOWED
            : ObjectInputFilter.Status.REJECTED;
};
```

Nếu object graph thực tế cần thêm class, hãy xác định lý do và bổ sung class cụ thể. Chuỗi được validate độ dài riêng sau khi đọc.

### Bài 3 — Phân biệt filter và validation

Một object được filter cho phép nhưng có `quantity = -10`. Vì sao filter không nhất thiết phát hiện lỗi này? Hãy viết bước kiểm tra nghiệp vụ sau khi deserialize.

### Bài 4 — Chọn cấu hình

Một ứng dụng có hai luồng: một luồng đọc DTO nội bộ, một luồng đọc message từ đối tác. Nêu cách tổ chức filter toàn JVM, filter riêng cho stream và filter factory để mỗi luồng có allowlist phù hợp mà vẫn giữ giới hạn chung.

### Bài 5 — Đánh giá phương án thay thế

Một hệ thống muốn thay Java serialization bằng JSON. Hãy nêu các lợi ích và những cấu hình vẫn cần kiểm soát (schema, polymorphic typing, độ sâu, kích thước, validation).

## 15. Tài liệu chính thức của Java 17

- [Java SE 17 API — ObjectInputFilter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputFilter.html): filter status, FilterInfo, giới hạn object graph và phương thức lọc.
- [Java SE 17 API — ObjectInputFilter.Config](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputFilter.Config.html): cấu hình global filter, pattern filter và filter factory.
- [Java SE 17 API — ObjectInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputStream.html): quy trình đọc object và cài filter cho từng stream.
- [JEP 290 — Filter Incoming Serialization Data](https://openjdk.org/jeps/290): cơ chế lọc dữ liệu serialization, giới hạn graph và pattern filter.
- [JEP 415 — Context-Specific Deserialization Filters](https://openjdk.org/jeps/415): filter factory theo context, được đưa vào Java 17.
- [Oracle Secure Coding Guidelines — Serialization and Deserialization](https://www.oracle.com/java/technologies/javase/seccodeguide.html): hướng dẫn bảo mật cho xử lý serialization.

**Ghi nhớ:** Đọc object stream là dựng object graph và có thể kích hoạt callback của class. Dữ liệu không đáng tin cậy có thể dẫn đến gadget chain, DoS hoặc trạng thái nghiệp vụ không hợp lệ. Mặc định nên tránh Java native deserialization từ nguồn không tin cậy. Nếu buộc phải duy trì, dùng `ObjectInputFilter` với allowlist hẹp và giới hạn graph, cài filter trước khi đọc, xác thực nguồn/tính toàn vẹn khi cần và kiểm tra dữ liệu nghiệp vụ sau khi deserialize. JEP 415 trong Java 17 bổ sung filter factory để áp dụng chính sách theo context; nó không biến deserialization tùy ý thành an toàn.
