# Thực hành Java I/O: Serialization và cấu hình ObjectInputFilter

## Mục tiêu

Sau bài thực hành, bạn có thể: (1) tuần tự hóa đối tượng Java thành luồng byte và khôi phục lại đối tượng; (2) hiểu vai trò của Serializable, serialVersionUID và transient; (3) cấu hình ObjectInputFilter để giới hạn kiểu đối tượng và quy mô đồ thị được giải tuần tự hóa; (4) phân biệt luồng hợp lệ, luồng bị bộ lọc từ chối và luồng hỏng; (5) biết những giới hạn bảo mật của Java serialization.

**Bối cảnh:** Đây là bài thực hành trong Java Core I/O. Dùng JDK 17 trở lên, không cần framework hay thư viện ngoài JDK.

## 1. Cơ chế cần hiểu trước khi chạy

**Serialization (tuần tự hóa)** chuyển trạng thái đủ điều kiện của một đối tượng thành dạng byte bằng ObjectOutputStream. **Deserialization (giải tuần tự hóa)** dùng ObjectInputStream để đọc luồng byte và tái dựng đồ thị đối tượng. Cùng một luồng có thể chứa nhiều đối tượng; các tham chiếu dùng chung và một số quan hệ vòng được giao thức serialization quản lý.

Luồng xử lý trong ví dụ:

~~~text
Account("Lan", token="SECRET")
  -> ObjectOutputStream.writeObject(...)
  -> byte[] chứa Java serialization stream
  -> ByteArrayInputStream
  -> ObjectInputStream + ObjectInputFilter
  -> readObject()
      -> ALLOWED  : Account được đọc, token transient thành null
      -> REJECTED : lớp không nằm trong allowlist bị InvalidClassException
~~~

Các điểm cần nhớ:

- Một lớp tự định nghĩa phải triển khai Serializable để được ghi theo cơ chế mặc định; đây là interface đánh dấu, không chứa phương thức cần override. Đối tượng trong các trường không transient cũng phải có khả năng được serialize nếu chúng được duyệt đến; nếu không có thể phát sinh NotSerializableException.
- ObjectOutputStream ghi một định dạng nhị phân đặc thù của Java. ObjectInputStream đọc lại định dạng này; không thể coi nó là JSON, văn bản UTF-8 hay cách trao đổi dữ liệu đa ngôn ngữ.
- serialVersionUID xác định phiên bản lớp phục vụ kiểm tra tương thích khi đọc. Tự khai báo giá trị ổn định giúp kiểm soát thay đổi lớp, nhưng **không** bảo đảm mọi thay đổi schema đều tương thích.
- Trường instance được đánh dấu transient không được serialize theo cơ chế mặc định; khi đọc lại nó nhận giá trị mặc định của kiểu (ví dụ null đối với String). Trường static cũng không thuộc trạng thái instance được serialize.
- ObjectInputFilter được gọi **trong quá trình deserialization** để xét lớp, kích thước mảng, độ sâu đồ thị, số tham chiếu và số byte đã đọc. Nó không được áp dụng khi chỉ gọi writeObject và không phải công cụ mã hóa hay xác thực dữ liệu.

## 2. Chương trình đầy đủ: chấp nhận đúng lớp, từ chối lớp khác

Tạo một tệp duy nhất mang tên **SerializationFilterDemo.java** với nội dung dưới đây. Hai lớp dữ liệu được khai báo lồng bên trong lớp main để toàn bộ bài chạy bằng một tệp.

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InvalidClassException;
import java.io.ObjectInputFilter;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.Serial;
import java.io.Serializable;

public class SerializationFilterDemo {

    private static final class Account implements Serializable {
        @Serial
        private static final long serialVersionUID = 1L;

        private final String owner;
        private final transient String sessionToken;

        Account(String owner, String sessionToken) {
            this.owner = owner;
            this.sessionToken = sessionToken;
        }

        @Override
        public String toString() {
            return "Account[owner=" + owner
                    + ", sessionToken=" + sessionToken + "]";
        }
    }

    private static final class Unexpected implements Serializable {
        @Serial
        private static final long serialVersionUID = 1L;

        private final String label;

        Unexpected(String label) {
            this.label = label;
        }
    }

    private static byte[] serialize(Serializable value) throws IOException {
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        try (ObjectOutputStream out = new ObjectOutputStream(buffer)) {
            out.writeObject(value);
        }
        return buffer.toByteArray();
    }

    private static Object deserializeWithFilter(byte[] bytes)
            throws IOException, ClassNotFoundException {
        try (ObjectInputStream in = new ObjectInputStream(
                new ByteArrayInputStream(bytes))) {

            String pattern = "maxdepth=5;maxrefs=20;maxbytes=4096;"
                    + "maxarray=100;SerializationFilterDemo$Account;!*";
            ObjectInputFilter filter =
                    ObjectInputFilter.Config.createFilter(pattern);

            // Thiết lập filter trước lệnh readObject() đầu tiên.
            in.setObjectInputFilter(filter);
            return in.readObject();
        }
    }

    public static void main(String[] args) throws Exception {
        byte[] acceptedBytes =
                serialize(new Account("Lan", "SECRET"));
        Object accepted = deserializeWithFilter(acceptedBytes);
        System.out.println("Accepted: " + accepted);

        byte[] rejectedBytes =
                serialize(new Unexpected("not allowed"));
        try {
            deserializeWithFilter(rejectedBytes);
            System.out.println("Unexpected object accepted");
        } catch (InvalidClassException rejected) {
            System.out.println("Rejected by ObjectInputFilter");
        }
    }
}
~~~

Biên dịch và chạy từ thư mục chứa tệp:

~~~bash
javac SerializationFilterDemo.java
java SerializationFilterDemo
~~~

Kết quả mong đợi với JDK 17+ mặc định:

~~~text
Accepted: Account[owner=Lan, sessionToken=null]
Rejected by ObjectInputFilter
~~~

**Giải thích kết quả:**

1. serialize(...) tạo ByteArrayOutputStream, bọc bằng ObjectOutputStream rồi writeObject(value). Kết quả byte[] là dữ liệu thật đã tuần tự hóa, chưa được giải mã và không phải chuỗi ký tự.
2. deserializeWithFilter(...) tạo ObjectInputStream, cài bộ lọc bằng setObjectInputFilter(...) **trước khi** gọi readObject().
3. Lớp Account được allowlist nên được tái dựng. owner có giá trị "Lan"; sessionToken là transient nên nhận null, dù trước lúc ghi mang giá trị "SECRET".
4. Luồng Unexpected vẫn được serialize thành công vì Unexpected implements Serializable; khi giải tuần tự hóa, bộ lọc gặp lớp Unexpected, quy tắc cuối !* từ chối, ObjectInputStream phát sinh InvalidClassException.
5. Code chỉ bắt InvalidClassException cho trường hợp bộ lọc từ chối. Trong ứng dụng thực, IOException, ClassNotFoundException và lỗi dữ liệu khác phải được xử lý riêng theo ngữ cảnh; không quy mọi lỗi readObject thành lỗi lọc.

**Lưu ý về lớp lồng:** tên nhị phân của Account là SerializationFilterDemo$Account, không phải SerializationFilterDemo.Account. Vì vậy chuỗi pattern phải sử dụng dấu $. Nếu chuyển Account sang package com.example.io với lớp top-level, pattern cần dùng đúng tên đầy đủ com.example.io.Account.

## 3. Phân tích ObjectInputFilter từng bước

ObjectInputFilter là một interface được JDK cung cấp để tham gia quyết định khi ObjectInputStream tạo/đọc đối tượng từ luồng. Nó kiểm tra thông tin của đối tượng đang được đọc qua FilterInfo:

| Thuộc tính FilterInfo | Ý nghĩa | Cách dùng |
| --- | --- | --- |
| serialClass() | Class đang được kiểm tra; đôi lúc null ở các lần kiểm tra không gắn với lớp mới | Chỉ quyết định theo class khi khác null |
| arrayLength() | Độ dài mảng nếu đang xét mảng; thường -1 nếu không phải mảng | Chặn mảng quá lớn |
| depth() | Độ sâu hiện tại của đồ thị đối tượng | Hạn chế đồ thị lồng quá sâu |
| references() | Số tham chiếu mà luồng đã xử lý | Hạn chế số đối tượng/tham chiếu |
| streamBytes() | Lượng byte đã tiêu thụ tại thời điểm kiểm tra | Hạn chế dung lượng đã đọc |

Bộ lọc trả về một trong ba giá trị:

- **ALLOWED**: cho phép đối tượng/lớp đang xét đi tiếp.
- **REJECTED**: từ chối; quá trình giải tuần tự hóa sẽ thất bại (thường dưới dạng InvalidClassException).
- **UNDECIDED**: bộ lọc chưa quyết định. Giá trị này **không mặc nhiên có nghĩa là cấm**; nếu các bộ lọc khác hoặc chính sách hiệu lực không từ chối, việc đọc có thể vẫn tiếp diễn.

Mẫu cài đặt bằng pattern trong chương trình:

~~~text
maxdepth=5;maxrefs=20;maxbytes=4096;maxarray=100;SerializationFilterDemo$Account;!*
~~~

Bốn giới hạn được kiểm tra trước các luật lớp:

| Thành phần | Vai trò |
| --- | --- |
| maxdepth=5 | Từ chối khi độ sâu vượt 5 |
| maxrefs=20 | Từ chối khi số tham chiếu vượt 20 |
| maxbytes=4096 | Từ chối khi số byte đã đọc vượt 4.096 |
| maxarray=100 | Từ chối khi độ dài một mảng vượt 100 |
| SerializationFilterDemo$Account | Cho phép lớp Account trong chương trình |
| !* | Từ chối tất cả lớp còn lại phù hợp ký tự đại diện * |

**Thứ tự luật lớp quan trọng.** Với cùng một lớp, mẫu khớp đầu tiên quyết định. Nếu đặt !* ở đầu, Account cũng bị từ chối. Các giới hạn maxdepth/maxrefs/maxbytes/maxarray được kiểm tra độc lập với vị trí luật lớp. Ký tự khoảng trắng trong pattern là có ý nghĩa; không tự ý viết khoảng trắng quanh dấu chấm phẩy hoặc tên lớp.

Trong ví dụ, whitelist hẹp phù hợp vì đồ thị Account chỉ chứa trường String và các giá trị đơn giản. Lời gọi bộ lọc không áp dụng cho các primitive hoặc String được mã hóa trực tiếp theo giao thức serialization; vì vậy **đừng suy diễn rằng whitelist lớp đủ kiểm soát mọi dữ liệu của mọi kiểu**. Khi mô hình có List, Map, mảng hay lớp lồng, phải kiểm tra cả những lớp thực sự xuất hiện trong luồng, các dạng nội bộ và tài nguyên có thể được phân bổ.

## 4. Thử nghiệm có kiểm soát

### 4.1. Thấy tác dụng của transient

Trong chương trình, đổi giá trị khi tạo đối tượng:

~~~java
serialize(new Account("Minh", "TOKEN-123"))
~~~

Khi chạy lại, phần Account của output sẽ cho thấy owner=Minh và sessionToken=null. transient giúp không lưu **trường đó** trong luồng theo cơ chế mặc định; nó không xóa dữ liệu đang nằm ở nơi khác, và các phương thức writeObject tùy biến có thể thay đổi dữ liệu được ghi. Tuyệt đối không dùng transient làm biện pháp bảo vệ duy nhất cho bí mật.

### 4.2. Chặn cả Account bằng chính sách lớp

Thay pattern thành:

~~~java
String pattern = "maxdepth=5;maxrefs=20;maxbytes=4096;"
        + "maxarray=100;!*";
~~~

Lúc này ngay cả Account cũng bị từ chối. Trong chương trình hiện tại, lệnh deserializeWithFilter(acceptedBytes) đầu tiên sẽ phát sinh InvalidClassException trước khi tới phần catch dành cho Unexpected. Để quan sát thông báo thân thiện, bắt exception cho nhánh đầu hoặc hoàn nguyên pattern sau thí nghiệm.

### 4.3. Thử giới hạn kích thước mảng

Ví dụ độc lập về một mảng 101 phần tử:

~~~java
byte[] arrayBytes = serialize(new int[101]);
~~~

Để thử mảng này với cùng hàm deserializeWithFilter(...), có thể truyền arrayBytes; maxarray=100 sẽ chặn mảng quá dài. Nhưng hàm hiện dùng quy tắc !* nên mảng cũng có thể bị chặn bởi luật lớp, kể cả khi chưa vượt giới hạn. Để kiểm tra **riêng** maxarray, dùng một filter minh họa như:

~~~java
ObjectInputFilter arrayFilter =
        ObjectInputFilter.Config.createFilter("maxarray=100;*");
~~~

Cài arrayFilter vào ObjectInputStream mới **trước readObject()**, sau đó đọc các luồng int[100] và int[101]. Với JDK 17 mặc định, mảng 100 phần tử được chấp nhận và mảng 101 phần tử bị từ chối. Mẫu * cho phép mọi lớp, nên **chỉ dùng trong thí nghiệm giới hạn mảng**, không dùng làm chính sách bảo vệ dữ liệu không tin cậy.

### 4.4. Đổi ngưỡng bytes và depth

Giảm maxbytes từ 4096 xuống một giá trị nhỏ như 16 thường khiến luồng Account trong ví dụ bị từ chối trước khi khôi phục thành công. Tuy nhiên, giá trị bytes tại từng lần callback phụ thuộc thời điểm đọc; không coi con số ngưỡng này là độ dài tuyệt đối của mảng byte được serialize. Tương tự, với một đồ thị lồng nhiều lớp, giảm maxdepth có thể chặn việc đọc sâu. Không dùng một ngưỡng demo cố định cho mọi mô hình dữ liệu.

### 4.5. Phân biệt các nguyên nhân thất bại

| Hiện tượng | Nguyên nhân thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| InvalidClassException với thông điệp filter status | Bộ lọc từ chối một lớp hay giới hạn | Kiểm tra allowlist, giới hạn, thứ tự luật |
| InvalidClassException do serialVersionUID | Phiên bản lớp phía đọc và phía ghi không tương thích | Kiểm tra serialVersionUID và thay đổi schema |
| NotSerializableException khi ghi | Một đối tượng trong đồ thị không serializable | Kiểm tra các trường và kiểu liên quan |
| StreamCorruptedException / EOFException khi đọc | Luồng sai định dạng, thiếu hoặc bị cắt | Xác nhận đầu vào đúng Java serialized bytes |
| ClassNotFoundException khi đọc | Bên đọc thiếu lớp có tên trong luồng | Kiểm tra classpath/module và triển khai ứng dụng |

Một lỗi có thể được bao bọc bởi exception ở tầng gọi. Không nên phân loại chỉ dựa vào tên exception mà không xem thông điệp, cause và trạng thái chương trình.

## 5. Hai cách cấu hình ObjectInputFilter

### 5.1. Theo từng ObjectInputStream: phù hợp với bài thực hành

~~~java
ObjectInputFilter filter = ObjectInputFilter.Config.createFilter(
        "maxdepth=10;maxrefs=100;maxbytes=65536;maxarray=1000;"
                + "com.example.io.SafeMessage;!*");
try (ObjectInputStream in = new ObjectInputStream(inputStream)) {
    in.setObjectInputFilter(filter);
    Object value = in.readObject();
}
~~~

Đoạn trên chỉ minh họa phần đọc bên trong ứng dụng đã có inputStream, cùng lớp com.example.io.SafeMessage thật sự tồn tại. Nó **không phải chương trình độc lập**. Pattern cụ thể cần được xây dựng theo đồ thị đối tượng thực tế. Thiết lập filter trước readObject, close stream bằng try-with-resources và kiểm tra kiểu dữ liệu sau khi đọc.

### 5.2. Bộ lọc JVM-wide và filter factory

JDK hỗ trợ bộ lọc toàn JVM thông qua system property jdk.serialFilter hoặc security property tương ứng; ví dụ khởi chạy ứng dụng với giới hạn tổng quát:

~~~bash
java -Djdk.serialFilter=maxdepth=20;maxrefs=200;maxbytes=1048576 SerializationFilterDemo
~~~

**Chú ý shell:** dấu ; thường là ký tự đặc biệt của shell (đặc biệt trong PowerShell/Bash). Đặt toàn bộ tham số JVM trong dấu nháy để truyền nguyên giá trị:

~~~bash
java "-Djdk.serialFilter=maxdepth=20;maxrefs=200;maxbytes=1048576" SerializationFilterDemo
~~~

Các cấu hình này có phạm vi áp dụng rộng, vì vậy phải đánh giá ảnh hưởng tới tất cả luồng đọc đối tượng trong ứng dụng. Từ JDK 17, filter factory có thể kết hợp bộ lọc toàn JVM với bộ lọc trên từng stream; cách kết hợp thực tế phụ thuộc cấu hình factory. Không mặc định rằng setObjectInputFilter luôn ghi đè hoàn toàn một chính sách JVM-wide đã cài đặt. Để phân tích hành vi, kiểm tra tài liệu của đúng JDK và cấu hình runtime đang chạy.

**Nguyên tắc:** policy ứng dụng phải có allowlist và giới hạn tài nguyên phù hợp với từng luồng dữ liệu; policy JVM-wide là lớp hỗ trợ, không thay thế việc xác định mô hình dữ liệu mong đợi của từng điểm nhận input.

## 6. Khi cần filter viết bằng Java thay cho pattern

Pattern tiện cho luật theo tên lớp và giới hạn cơ bản. Nếu cần điều kiện ngữ cảnh, triển khai trực tiếp ObjectInputFilter. Đây là **đoạn minh họa** áp dụng cho lớp SafeMessage ở package com.example.io:

~~~java
ObjectInputFilter customFilter = info -> {
    if (info.depth() > 10
            || info.references() > 100
            || info.streamBytes() > 65_536
            || info.arrayLength() > 1_000) {
        return ObjectInputFilter.Status.REJECTED;
    }

    Class<?> type = info.serialClass();
    if (type == null) {
        return ObjectInputFilter.Status.UNDECIDED;
    }

    while (type.isArray()) {
        type = type.getComponentType();
    }

    if (type == com.example.io.SafeMessage.class) {
        return ObjectInputFilter.Status.ALLOWED;
    }
    return ObjectInputFilter.Status.REJECTED;
};
~~~

Ở đây, biểu thức arrayLength() > 1_000 không chặn trường hợp -1 (không phải mảng). serialClass() == null có thể xuất hiện trong các callback chỉ dùng để cập nhật giới hạn; trả UNDECIDED sau khi kiểm tra giới hạn là phù hợp trong nhánh này. Khi type khác null và không được phép, trả REJECTED để tránh khoảng trống allowlist.

Đây là mã minh họa logic lọc, cần lớp com.example.io.SafeMessage được khai báo trong dự án. Nếu kiểu hợp lệ chứa các phần tử bổ trợ (chẳng hạn một số collection, enum, mảng hoặc lớp lồng), phải lập allowlist đầy đủ trên cơ sở luồng thật và giới hạn tài nguyên; nếu không, chính dữ liệu hợp lệ sẽ bị từ chối.

## 7. Những hiểu lầm và lỗi phổ biến

1. **Chỉ kiểm tra instanceof sau readObject().** Quá muộn cho một số rủi ro: Java đã tiến hành giải tuần tự hóa trước khi phép kiểm tra kiểu trả về diễn ra. Đặt ObjectInputFilter trước readObject để từ chối sớm hơn trong phạm vi filter hỗ trợ.
2. **Cho rằng implements Serializable là dấu hiệu an toàn.** Interface này chỉ cho biết đối tượng có thể tham gia serialization, không khẳng định nguồn byte đáng tin hay nội dung hợp lệ.
3. **Dùng filter chỉ với maxdepth nhưng không giới hạn lớp.** Một policy tốt cần xét cả kiểu, kích thước mảng, số tham chiếu và byte; tùy trường hợp còn cần giới hạn ở tầng truyền tải trước khi tạo ObjectInputStream.
4. **Cho rằng UNDECIDED nghĩa là REJECTED.** Khi dùng rule pattern mà không có luật loại trừ cuối cùng, các lớp không khớp có thể vẫn được đọc.
5. **Dùng tên lớp sai.** Nested class sử dụng dấu $ trong tên nhị phân; package và tên module (nếu ghi trong pattern) phải chính xác.
6. **Viết !* trước allowlist.** Bộ lọc xét pattern theo thứ tự nên rule từ chối chung đặt trước sẽ che hết các rule cho phép phía sau.
7. **Tin rằng bộ lọc đảm bảo an toàn tuyệt đối.** Filter giảm bề mặt tấn công nhưng không kiểm chứng chữ ký, không ngăn mọi hành vi trong custom readObject/readResolve và không sửa lỗi trong thư viện. Dữ liệu không tin cậy cần được xem là nguồn rủi ro, kể cả khi có filter.
8. **Dùng serialize làm cách lưu dữ liệu ổn định lâu dài.** Thay đổi tên lớp, serialVersionUID, trường và classpath có thể gây mất tương thích. Với dữ liệu trao đổi lâu dài, cân nhắc schema rõ ràng như JSON/Protocol Buffers cùng validate, giới hạn kích thước và xác thực phù hợp.
9. **Log hoặc công khai bí mật trong đối tượng.** Dù trường transient không được ghi mặc định, việc in toString() trong ứng dụng có thể tiết lộ thông tin hiện có. Chỉ hiện giá trị demo phi nhạy cảm.

## 8. Checklist tự kiểm tra và câu hỏi mở rộng

Tự chạy lại chương trình, sau đó xác nhận:

- Tệp có tên SerializationFilterDemo.java, lệnh javac biên dịch thành công trên JDK 17+.
- ObjectOutputStream ghi được cả Account và Unexpected.
- Account được khôi phục khi policy cho phép; owner vẫn là Lan và sessionToken thành null.
- Unexpected bị từ chối khi readObject() dưới policy chứa allowlist Account và !*.
- Đổi thứ tự !* lên trước khiến Account cũng bị chặn.
- Bạn có thể giải thích maxdepth, maxrefs, maxbytes, maxarray và sự khác nhau giữa ALLOWED / REJECTED / UNDECIDED.
- Các thao tác đọc đối tượng từ nguồn không tin cậy trong ứng dụng đều có policy thích hợp, với giới hạn đầu vào ở lớp truyền tải và xử lý lỗi riêng.

**Câu hỏi suy ngẫm:** (1) Vì sao ép kiểu Account sau readObject không thay thế được ObjectInputFilter? (2) Vì sao trường transient trở thành null và khi nào cần custom serialization? (3) Bộ lọc theo tên lớp có thể thiếu những lớp hợp lệ nào khi Account chứa List hoặc mảng? (4) Vì sao maxbytes và maxrefs giúp giảm rủi ro tiêu thụ tài nguyên nhưng không chứng minh luồng đáng tin?

## Tài liệu tham khảo chính thức

- Oracle JDK 17 API — Serializable: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Serializable.html
- Oracle JDK 17 API — ObjectInputStream: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputStream.html
- Oracle JDK 17 API — ObjectInputFilter: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputFilter.html
- Oracle JDK 17 API — ObjectInputFilter.Config và cú pháp pattern: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputFilter.Config.html
- OpenJDK JEP 290 — Filter Incoming Serialization Data: https://openjdk.org/jeps/290
- OpenJDK JEP 415 — Context-Specific Deserialization Filters: https://openjdk.org/jeps/415
