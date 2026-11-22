# Tương thích dữ liệu: tệp, đối tượng tuần tự hóa và thông điệp

Trong một dự án Java, nâng cấp phiên bản ứng dụng thường diễn ra theo nhiều đợt. Một máy chủ mới có thể phải đọc dữ liệu do phiên bản cũ ghi ra; một tiến trình cũ có thể vẫn đang xử lý thông điệp do tiến trình mới gửi; hoặc một tệp được tạo từ nhiều năm trước vẫn cần mở được sau khi cấu trúc chương trình thay đổi. Những tình huống này đều thuộc về **tương thích dữ liệu**.

Tương thích dữ liệu là khả năng các phiên bản khác nhau của chương trình tiếp tục trao đổi, lưu trữ và diễn giải dữ liệu theo cùng một hợp đồng. Hợp đồng đó không chỉ gồm tên trường và kiểu dữ liệu. Nó còn bao gồm ý nghĩa của trường, cách mã hóa, quy tắc xử lý giá trị thiếu, đơn vị đo, định dạng ngày giờ và cách xử lý những phần dữ liệu mà một phiên bản chưa biết.

Bài học tập trung vào ba dạng dữ liệu thường gặp khi di chuyển ứng dụng Java: **tệp**, **đối tượng Java được tuần tự hóa** và **thông điệp giữa các thành phần**. Mỗi dạng có cơ chế tương thích riêng, nhưng đều cần một quy trình quản lý phiên bản rõ ràng.

## 1. Các khái niệm nền tảng

Giả sử phiên bản `v1` của ứng dụng ghi dữ liệu, sau đó phiên bản `v2` đọc dữ liệu đó. Ta cần phân biệt chiều tương thích:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Tương thích ngược (backward compatibility) | Bộ đọc mới hiểu được dữ liệu do bộ ghi cũ tạo ra. | `v2` đọc được tệp hoặc thông điệp của `v1`. |
| Tương thích xuôi (forward compatibility) | Bộ đọc cũ vẫn xử lý được dữ liệu do bộ ghi mới tạo ra. | `v1` bỏ qua trường mới mà `v2` bổ sung. |
| Tương thích hai chiều (full compatibility) | Cả bộ đọc mới và cũ đều xử lý được dữ liệu của nhau trong phạm vi đã cam kết. | Các phiên bản có thể được triển khai xen kẽ trong một giai đoạn nâng cấp. |

Tên gọi có thể được dùng khác nhau giữa các nhóm hoặc công cụ. Vì vậy, khi thiết kế một định dạng, hãy ghi rõ ma trận cụ thể: phiên bản ghi nào được phiên bản đọc nào hỗ trợ. Không nên chỉ ghi chung chung rằng định dạng “có tương thích”.

Ngoài cấu trúc, cần xét đến **tương thích ngữ nghĩa**. Ví dụ, trường `amount` vẫn là số thập phân ở cả hai phiên bản, nhưng `v1` hiểu là đồng Việt Nam còn `v2` hiểu là đô la Mỹ. Kiểu dữ liệu không đổi nhưng ý nghĩa đã đổi; đây vẫn là một thay đổi phá vỡ hợp đồng.

Một thay đổi thường an toàn hơn khi nó có đủ các đặc điểm sau:

- Trường mới có thể vắng mặt trong dữ liệu cũ và có giá trị mặc định hợp lý.
- Bộ đọc cũ có thể bỏ qua trường mới mà không làm sai kết quả nghiệp vụ.
- Trường hiện có giữ nguyên tên, kiểu, đơn vị và ý nghĩa.
- Định dạng có cách nhận biết phiên bản và có quy tắc xử lý phiên bản chưa hỗ trợ.

## 2. Tương thích của tệp

### 2.1. Tệp cũng là một hợp đồng dữ liệu

Một tệp được tạo bởi ứng dụng không chỉ là một tập byte. Nó có cấu trúc mà chương trình đọc phải hiểu. Với tệp văn bản, cấu trúc có thể gồm tên cột, dấu phân cách, thứ tự trường, encoding và quy tắc biểu diễn giá trị rỗng. Với tệp nhị phân, cấu trúc có thể gồm chữ ký, phiên bản, độ dài từng phần, thứ tự byte và mã kiểm tra.

Trước khi thay đổi định dạng tệp, hãy xác định các câu hỏi sau:

1. Tệp được mã hóa bằng UTF-8, UTF-16 hay encoding nào khác?
2. Ngày giờ có múi giờ hay chỉ là thời gian địa phương?
3. Số thập phân dùng dấu chấm hay dấu phẩy? Có quy định độ chính xác không?
4. Giá trị không có, giá trị `null`, chuỗi rỗng và số `0` có ý nghĩa khác nhau không?
5. Bộ đọc có được phép bỏ qua cột hoặc trường chưa biết không?
6. Nếu thiếu một trường bắt buộc, chương trình sẽ từ chối tệp hay dùng giá trị mặc định?
7. Có cần đọc lại những tệp được tạo bởi các phiên bản đã ngừng hỗ trợ không?

Những chi tiết tưởng như nhỏ này thường là nguyên nhân khiến một lần nâng cấp làm hỏng dữ liệu cũ.

### 2.2. Tệp văn bản và định dạng có cấu trúc

CSV, JSON, XML và các định dạng văn bản khác thuận tiện để kiểm tra bằng mắt, nhưng vẫn cần quy tắc phiên bản. Chẳng hạn, một tệp CSV ban đầu có các cột `id,name`; phiên bản mới thêm `email`. Bộ đọc mới có thể đọc tệp cũ nếu nó chấp nhận cột `email` bị thiếu. Ngược lại, bộ đọc cũ có thể không đọc được tệp mới nếu nó giả định tệp luôn có đúng hai cột hoặc phụ thuộc vào vị trí cột.

Đối với CSV, nên:

- Đặt tên cột ở dòng đầu và ánh xạ theo tên thay vì phụ thuộc tuyệt đối vào vị trí.
- Xác định rõ dấu phân cách, quy tắc escape dấu nháy và cách biểu diễn dòng mới trong một ô.
- Dùng UTF-8 và ghi rõ encoding trong tài liệu định dạng.
- Quy định cách xử lý cột không biết, cột bị thiếu và giá trị rỗng.
- Tránh thay đổi đơn vị hoặc ý nghĩa của cột hiện có.

Với JSON, có thể thêm một trường phiên bản vào tài liệu:

```json
{
  "formatVersion": 2,
  "customerId": "C-1042",
  "displayName": "Nguyen An",
  "email": "an@example.test"
}
```

Khi đọc, chương trình kiểm tra `formatVersion` rồi chuyển dữ liệu về mô hình nội bộ hiện tại. Nếu trường phiên bản không tồn tại, ứng dụng có thể xem đó là phiên bản `1` **chỉ khi hợp đồng cũ đã quy định rõ điều này**. Không nên tự suy đoán phiên bản chỉ từ một vài trường có mặt trong tệp.

JSON cho phép biểu diễn trường mới mà không làm thay đổi cú pháp của tài liệu, nhưng điều đó không tự động bảo đảm tương thích. Một thư viện phân tích có thể từ chối thuộc tính không biết; một trường mới có thể bị coi là bắt buộc; hoặc hai phiên bản có thể hiểu khác nhau về `null`. Hãy cấu hình và kiểm thử bộ đọc theo đúng chính sách của ứng dụng.

### 2.3. Tệp nhị phân cần có dấu hiệu nhận dạng và phiên bản

Với định dạng nhị phân do ứng dụng tự thiết kế, không nên chỉ ghi các trường nối tiếp nhau rồi kỳ vọng bộ đọc luôn biết cách diễn giải. Một cấu trúc đơn giản có thể bắt đầu bằng:

| Thành phần | Mục đích |
|---|---|
| Magic number / signature | Nhận biết đúng loại tệp. |
| Format version | Chọn bộ giải mã tương ứng. |
| Payload length | Kiểm tra độ dài dữ liệu và tránh đọc vượt giới hạn. |
| Payload | Nội dung thực tế. |
| Checksum (nếu cần) | Phát hiện dữ liệu bị hỏng ngoài ý muốn. |

Ví dụ sau minh họa cách kiểm tra phần đầu tệp bằng `DataInputStream`. Đây chỉ là ví dụ về header; phần giải mã payload cần được định nghĩa riêng cho từng phiên bản.

```java
import java.io.DataInputStream;
import java.io.IOException;

public final class FileHeaderReader {
    private static final int MAGIC = 0x43555354; // ASCII: CUST
    private static final int MAX_PAYLOAD_LENGTH = 20 * 1024 * 1024;

    public static int readVersion(DataInputStream input) throws IOException {
        int magic = input.readInt();
        if (magic != MAGIC) {
            throw new IOException("Not a supported customer file");
        }

        int version = input.readUnsignedShort();
        int payloadLength = input.readInt();

        if (payloadLength < 0 || payloadLength > MAX_PAYLOAD_LENGTH) {
            throw new IOException("Invalid payload length: " + payloadLength);
        }

        if (version != 1 && version != 2) {
            throw new IOException("Unsupported file version: " + version);
        }

        return version;
    }
}
```

`DataInputStream.readInt()` đọc bốn byte theo thứ tự big-endian. Nếu định dạng được dùng bởi nhiều ngôn ngữ hoặc nền tảng, thứ tự byte và kích thước từng trường phải là một phần của đặc tả, không nên dựa vào mặc định ngầm của một chương trình Java.

Khi đã nhận biết phiên bản, có thể tách bộ giải mã:

```java
switch (version) {
    case 1:
        return readVersion1(input);
    case 2:
        return readVersion2(input);
    default:
        throw new IOException("Unsupported version: " + version);
}
```

Hai bộ giải mã có thể tạo ra cùng một mô hình nội bộ hiện tại. Cách này giữ cho phần nghiệp vụ không phải biết mọi chi tiết của định dạng lịch sử.

### 2.4. Chiến lược di chuyển tệp cũ

Khi cần nâng cấp hàng loạt tệp, hãy tách hai thao tác: **đọc định dạng cũ** và **ghi định dạng mới**. Quy trình điển hình là:

1. Đọc tệp và xác định phiên bản.
2. Giải mã thành mô hình trung gian hoặc mô hình nghiệp vụ hiện tại.
3. Kiểm tra các trường bắt buộc và chuyển đổi đơn vị, ngày giờ hoặc giá trị mặc định theo quy tắc đã công bố.
4. Ghi ra tệp tạm theo định dạng mới.
5. Đọc lại hoặc xác minh tệp tạm, sau đó mới thay thế tệp đích.
6. Lưu bản sao lưu hoặc nhật ký đủ để truy vết và khôi phục khi cần.

Việc ghi qua tệp tạm giúp tránh để lại một tệp đích bị ghi dở nếu tiến trình dừng giữa chừng. Có thể dùng `Files.move` với `StandardCopyOption.ATOMIC_MOVE` khi hệ thống tệp hỗ trợ; cần có cách xử lý khi thao tác nguyên tử không được hỗ trợ. Không xóa bản gốc trước khi bản mới được xác minh.

Một tác vụ di chuyển nên có tính **idempotent**: chạy lại không làm dữ liệu bị chuyển đổi thêm lần nữa. Có thể đạt điều đó bằng cách ghi phiên bản mới vào header, kiểm tra phiên bản trước khi chuyển đổi và ghi nhận trạng thái theo từng tệp. Với số lượng tệp lớn, cần có báo cáo số tệp thành công, thất bại và bị bỏ qua.

Nếu tệp cũ vẫn có thể được tạo ra trong lúc nâng cấp, cần xác định thời điểm ngừng ghi định dạng cũ. Nếu không, một đợt di chuyển có thể hoàn tất nhưng dữ liệu mới lại tiếp tục xuất hiện ở định dạng cũ.

## 3. Tương thích của đối tượng Java được tuần tự hóa

### 3.1. Java Serialization lưu những gì?

Java Serialization cho phép ghi một đồ thị đối tượng vào luồng byte và dựng lại đồ thị đó bằng `ObjectOutputStream` và `ObjectInputStream`. Một lớp thường tham gia cơ chế này bằng cách triển khai `Serializable`:

```java
import java.io.Serializable;

public class Customer implements Serializable {
    private static final long serialVersionUID = 1L;

    private String id;
    private String name;
    private String email;
}
```

Luồng tuần tự hóa chứa thông tin cần thiết để nhận diện lớp và khôi phục trạng thái của đối tượng. Khi đọc, Java cần tìm được lớp tương ứng và kiểm tra mức tương thích của mô tả lớp trong luồng với lớp đang có trong chương trình.

Đây là điểm khác biệt quan trọng giữa Java Serialization và một định dạng trao đổi độc lập như JSON hoặc Protocol Buffers: dữ liệu tuần tự hóa của Java gắn khá chặt với tên lớp, cấu trúc lớp và quy tắc serialization của Java. Vì vậy, nó phù hợp với một số trường hợp lưu trạng thái nội bộ có kiểm soát, nhưng thường không phải lựa chọn tốt cho hợp đồng dữ liệu dài hạn giữa nhiều hệ thống hoặc nhiều ngôn ngữ.

### 3.2. Vai trò của `serialVersionUID`

`serialVersionUID` là mã định danh phiên bản của lớp có thể tuần tự hóa. Khi đọc một đối tượng, Java so sánh UID trong luồng với UID của lớp hiện tại. Nếu hai giá trị không khớp, quá trình đọc thường thất bại bằng `InvalidClassException`.

Nên khai báo UID tường minh:

```java
private static final long serialVersionUID = 1L;
```

Nếu không khai báo, Java có thể tính UID mặc định từ một số đặc điểm của lớp. Những thay đổi cấu trúc tưởng như nhỏ có thể làm giá trị được tính ra thay đổi, khiến dữ liệu cũ không đọc được sau khi biên dịch lại.

Giữ nguyên UID không có nghĩa mọi thay đổi đều an toàn. UID chỉ tham gia kiểm tra phiên bản lớp; nó không tự chuyển đổi dữ liệu, không bảo đảm ý nghĩa các trường không đổi và không thay thế việc kiểm tra tương thích. Nếu thay đổi thực sự không tương thích, việc đổi UID có thể giúp phát hiện lỗi sớm, nhưng ứng dụng vẫn cần một đường di chuyển dữ liệu riêng.

### 3.3. Những thay đổi lớp và ảnh hưởng đến dữ liệu cũ

Với các lớp `Serializable` thông thường, một số thay đổi có thể được Java xử lý theo quy tắc mặc định:

| Thay đổi | Hành vi thường gặp khi đọc luồng cũ | Điều cần chú ý |
|---|---|---|
| Thêm trường instance | Trường mới nhận giá trị mặc định của kiểu nếu luồng cũ không có trường đó. | `null`, `0` hoặc `false` có thể không phải giá trị nghiệp vụ mong muốn. |
| Xóa trường instance | Giá trị trường có trong luồng nhưng không còn trong lớp hiện tại bị bỏ qua. | Dữ liệu đó không còn được giữ trong đối tượng mới. |
| Đổi tên trường | Được xem như trường cũ biến mất và trường mới được thêm vào. | Giá trị cũ không tự động chuyển sang tên mới. |
| Đổi kiểu trường | Thường không tương thích và có thể gây lỗi khi đọc. | Cần chuyển đổi bằng cơ chế có chủ đích hoặc định dạng trung gian. |
| Thay đổi `serialVersionUID` | UID không khớp khiến Java từ chối đọc lớp. | Cần triển khai chiến lược di chuyển thay vì chỉ đổi UID. |

Ví dụ, phiên bản đầu có:

```java
public class Customer implements Serializable {
    private static final long serialVersionUID = 1L;
    private String name;
}
```

Phiên bản sau thêm `email`:

```java
public class Customer implements Serializable {
    private static final long serialVersionUID = 1L;
    private String name;
    private String email;
}
```

Khi đọc một luồng được tạo từ lớp cũ, `email` sẽ nhận `null` nếu luồng không chứa trường này. Nếu nghiệp vụ yêu cầu một giá trị mặc định như `"unknown"`, chương trình phải đặt giá trị đó trong quá trình khôi phục hoặc sau khi đọc. Không nên mặc định rằng giá trị mặc định của Java luôn là giá trị hợp lệ của nghiệp vụ.

Các thay đổi liên quan đến lớp cha, lớp con, kiểu enum, trường `static`, trường `transient` hoặc cơ chế serialization tùy chỉnh có quy tắc riêng. Khi cấu trúc kế thừa thay đổi, hãy kiểm tra đặc tả serialization cho đúng trường hợp và kiểm thử bằng luồng dữ liệu thực tế được tạo từ phiên bản cũ.

### 3.4. Dùng `readObject` để chuyển đổi trạng thái cũ

Một lớp có thể định nghĩa phương thức `readObject` riêng để kiểm soát cách khôi phục trạng thái. `ObjectInputStream.GetField` cho phép kiểm tra trường có trong luồng hay không và cung cấp giá trị mặc định khi trường chưa tồn tại.

```java
import java.io.IOException;
import java.io.ObjectInputStream;
import java.io.Serializable;

public class Customer implements Serializable {
    private static final long serialVersionUID = 1L;

    private String name;
    private String email;
    private String status;

    private void readObject(ObjectInputStream input)
            throws IOException, ClassNotFoundException {
        ObjectInputStream.GetField fields = input.readFields();

        name = (String) fields.get("name", null);
        email = (String) fields.get("email", null);

        if (fields.defaulted("status")) {
            status = "ACTIVE";
        } else {
            status = (String) fields.get("status", "ACTIVE");
        }
    }
}
```

Trong ví dụ này, luồng cũ không có `status` nên đối tượng sau khi đọc được gán `ACTIVE`. Đây là quyết định nghiệp vụ của ví dụ; hệ thống thực tế phải chọn giá trị mặc định dựa trên dữ liệu và quy tắc lịch sử. Nếu không thể suy ra giá trị an toàn, nên đánh dấu bản ghi cần xử lý hoặc từ chối dữ liệu thay vì âm thầm gán một trạng thái có thể gây sai lệch.

Một số cơ chế liên quan khác:

- `writeObject` tùy chỉnh cách ghi trạng thái.
- `serialPersistentFields` khai báo tập trường serialization ổn định, tách một phần tên trường lưu trữ khỏi cấu trúc trường nội bộ.
- `writeReplace` và `readResolve` thay thế đối tượng trong quá trình ghi hoặc đọc, hữu ích trong một số mô hình như singleton hoặc proxy.

Các cơ chế này làm serialization linh hoạt hơn nhưng cũng tăng độ phức tạp. Cần có fixture kiểm thử được tạo bởi phiên bản cũ để chứng minh dữ liệu vẫn được khôi phục đúng.

### 3.5. Giới hạn và an toàn của Java Serialization

Không nên xem một luồng Java Serialization là dữ liệu vô hại. Việc giải tuần tự hóa có thể khởi tạo nhiều đối tượng và kích hoạt logic trong các lớp liên quan. Không đọc dữ liệu tuần tự hóa tùy ý từ nguồn không đáng tin cậy. Nếu buộc phải duy trì cơ chế này, hãy giới hạn kiểu được phép giải tuần tự hóa bằng `ObjectInputFilter`, đồng thời giới hạn độ sâu đồ thị, số tham chiếu và kích thước mảng phù hợp với ứng dụng.

Với dữ liệu cần tồn tại lâu dài, được trao đổi qua mạng hoặc được dùng bởi nhiều ngôn ngữ, hãy cân nhắc một định dạng có schema và quy tắc tiến hóa rõ ràng. Có thể giữ Java Serialization cho dữ liệu nội bộ trong thời gian ngắn, nhưng cần biết chính xác nơi lưu, phiên bản nào tạo ra dữ liệu và thời hạn hỗ trợ.

## 4. Tương thích của thông điệp

### 4.1. Thông điệp là hợp đồng giữa các thành phần độc lập

Thông điệp xuất hiện trong REST API, hàng đợi, hệ thống publish/subscribe, Kafka, các tác vụ nền và tích hợp giữa dịch vụ. Người gửi (producer) và người nhận (consumer) có thể được triển khai ở thời điểm khác nhau. Trong một đợt triển khai cuốn chiếu, hai phiên bản có thể cùng tồn tại.

Vì vậy, cần kiểm tra ít nhất bốn trường hợp:

| Producer | Consumer | Câu hỏi cần trả lời |
|---|---|---|
| Cũ | Cũ | Hệ thống hiện tại có tiếp tục hoạt động không? |
| Cũ | Mới | Consumer mới có đọc được thông điệp đang tồn tại trong hàng đợi không? |
| Mới | Cũ | Consumer cũ có xử lý được thông điệp mới trong giai đoạn triển khai xen kẽ không? |
| Mới | Mới | Các thành phần mới có cùng cách hiểu schema và ý nghĩa dữ liệu không? |

Trường hợp cũ gửi cho consumer mới thường cần thiết để xử lý thông điệp tồn đọng. Trường hợp mới gửi cho consumer cũ thường quyết định liệu có thể triển khai producer trước hay không.

### 4.2. Thiết kế payload có thể tiến hóa

Một thông điệp nên có cấu trúc rõ ràng và giữ ổn định ý nghĩa của các trường. Ví dụ:

```json
{
  "eventType": "CustomerAddressChanged",
  "schemaVersion": 2,
  "eventId": "evt-8f31",
  "occurredAt": "2026-11-12T08:30:00Z",
  "payload": {
    "customerId": "C-1042",
    "address": {
      "city": "Ho Chi Minh City",
      "countryCode": "VN"
    }
  }
}
```

Envelope bên ngoài cung cấp loại sự kiện, phiên bản schema, mã định danh và thời điểm phát sinh. Payload chứa dữ liệu nghiệp vụ. Consumer có thể định tuyến theo `eventType` và chọn bộ giải mã theo `schemaVersion`.

Một số quy tắc thiết kế hữu ích:

- Thêm trường tùy chọn thường dễ tương thích hơn xóa hoặc đổi kiểu trường hiện có.
- Quy định giá trị mặc định khi trường mới vắng mặt.
- Giữ nguyên ý nghĩa của trường. Nếu ý nghĩa thay đổi, tạo trường mới hoặc loại sự kiện mới.
- Với enum, consumer nên có chiến lược cho giá trị chưa biết, chẳng hạn lưu lại, bỏ qua có kiểm soát hoặc chuyển sang nhánh `UNKNOWN`.
- Dùng định dạng thời gian có múi giờ, thường là ISO-8601 ở UTC, thay vì chuỗi thời gian địa phương không rõ múi giờ.
- Quy định đơn vị cho tiền, khoảng cách, khối lượng và các đại lượng khác. Không đổi đơn vị trong cùng một trường mà không đổi hợp đồng.
- Với số tiền hoặc số thập phân cần độ chính xác, quy định rõ cách biểu diễn và độ chính xác; không dựa vào cách làm tròn ngầm của từng nền tảng.
- Không dùng tên lớp Java làm hợp đồng thông điệp công khai. Tên lớp có thể thay đổi khi refactor mà không nên buộc mọi producer và consumer đổi theo.

Đối với JSON, consumer có thể được cấu hình để bỏ qua thuộc tính chưa biết. Tuy nhiên, chính sách này phải được kiểm thử trong thư viện đang dùng. Bỏ qua trường mới chỉ an toàn khi trường đó không cần thiết để giữ đúng hành vi nghiệp vụ của consumer cũ.

### 4.3. Schema và quy tắc tiến hóa

Khi số lượng producer và consumer tăng, việc chỉ dựa vào tài liệu JSON có thể không đủ. Schema giúp mô tả kiểu dữ liệu, trường bắt buộc, giá trị mặc định và các quy tắc tương thích.

**Protocol Buffers (Protobuf)** dùng số hiệu trường (field number) trong wire format. Khi đã phát hành schema, không được tự ý đổi số hiệu trường đang dùng hoặc tái sử dụng số hiệu của trường đã xóa. Nên đánh dấu số hiệu và tên trường đã ngừng dùng là `reserved`. Thêm trường mới với số hiệu mới thường là thay đổi tương thích, miễn là không làm thay đổi ý nghĩa hoặc vi phạm quy tắc wire type. Không nên đổi kiểu chỉ vì hai kiểu có vẻ gần giống nhau trong mã Java.

**Avro** hỗ trợ tiến hóa schema thông qua việc so khớp writer schema và reader schema. Reader có thể đọc dữ liệu được ghi bằng schema cũ nếu quy tắc phân giải cho phép. Giá trị mặc định của trường mới trong reader schema có vai trò quan trọng khi writer schema chưa có trường đó.

**JSON Schema** và các cơ chế schema cho JSON có thể kiểm tra cấu trúc payload, nhưng mức tương thích phụ thuộc vào cách định nghĩa schema và cấu hình consumer. Ví dụ, thêm một thuộc tính tùy chọn thường ít rủi ro hơn thêm một thuộc tính bắt buộc mà dữ liệu cũ không có.

Nếu sử dụng schema registry, cần quy định chính sách kiểm tra khi đăng ký schema mới: backward, forward, full hoặc một biến thể tương ứng với nền tảng. Chính sách phải phù hợp với thứ tự triển khai thực tế và thời gian lưu thông điệp. Một thông điệp có thể nằm trong hàng đợi hoặc log lâu hơn thời gian triển khai một phiên bản ứng dụng.

### 4.4. Triển khai thay đổi thông điệp theo từng bước

Giả sử cần thêm trường `preferredLanguage` vào sự kiện khách hàng. Một trình tự an toàn thường là:

1. **Nâng cấp consumer trước.** Consumer mới đọc được thông điệp cũ không có `preferredLanguage`, đồng thời hiểu được trường này khi nó xuất hiện.
2. **Triển khai consumer mới.** Trong giai đoạn này, producer vẫn gửi định dạng cũ nên consumer mới phải xử lý bình thường.
3. **Nâng cấp producer.** Producer bắt đầu gửi `preferredLanguage`; nếu cần tương thích với consumer cũ, trường mới phải được consumer cũ bỏ qua an toàn.
4. **Theo dõi và chờ hết thời gian chuyển tiếp.** Kiểm tra lỗi giải mã, thông điệp vào dead-letter queue và các consumer chưa được nâng cấp.
5. **Ngừng trường cũ sau khi xác nhận không còn người đọc cần nó.** Nếu cần xóa trường, thực hiện trong một đợt thay đổi riêng và tuân thủ thời gian lưu trữ, phát lại thông điệp.

Nếu thay đổi phá vỡ tương thích, chẳng hạn đổi ý nghĩa hoặc cấu trúc cốt lõi, hãy cân nhắc tạo loại sự kiện mới hoặc kênh phiên bản mới như `CustomerAddressChangedV2`. Consumer có thể hỗ trợ cả hai loại trong giai đoạn chuyển tiếp. Không nên âm thầm gửi cấu trúc mới dưới tên sự kiện cũ rồi hy vọng mọi consumer đều hiểu.

Với hệ thống cần phát lại sự kiện, hãy kiểm tra cả dữ liệu lịch sử. Consumer mới có thể phải đọc thông điệp đã lưu từ nhiều tháng trước, không chỉ payload mới nhất. Nếu schema cũ không còn được hỗ trợ, cần có bước chuyển đổi lịch sử hoặc giữ bộ giải mã tương ứng.

## 5. So sánh ba dạng dữ liệu

| Tiêu chí | Tệp | Java Serialization | Thông điệp |
|---|---|---|---|
| Phạm vi thường gặp | Lưu trữ, trao đổi theo lô, import/export | Lưu trạng thái đối tượng nội bộ | Giao tiếp giữa dịch vụ hoặc tiến trình |
| Cách nhận biết phiên bản | Header, metadata, tên schema hoặc trường version | `serialVersionUID` và mô tả lớp trong luồng | Schema version, event type, schema registry |
| Rủi ro chính | Encoding, thứ tự cột, cấu trúc byte, dữ liệu cũ | Ràng buộc với lớp Java và thay đổi cấu trúc lớp | Producer/consumer triển khai lệch phiên bản, thông điệp tồn đọng |
| Hướng xử lý phổ biến | Bộ đọc theo phiên bản và chuyển đổi tệp | `readObject` có kiểm soát hoặc chuyển sang DTO/định dạng khác | Schema evolution và triển khai consumer/producer theo thứ tự |
| Kiểm thử quan trọng | Fixture tệp từ các phiên bản trước | Luồng serialization cũ được lưu làm fixture | Contract test và replay thông điệp lịch sử |

Không có một chiến lược duy nhất phù hợp cho cả ba. Tệp thường cần quy trình di chuyển và lưu trữ; Java Serialization cần kiểm soát chặt phiên bản lớp; thông điệp cần phối hợp lịch triển khai giữa nhiều thành phần.

## 6. Quy trình thực hiện khi nâng cấp dữ liệu trong ứng dụng Java

Một quy trình thực tế có thể chia thành các bước sau:

### Bước 1: Kiểm kê nguồn dữ liệu

Liệt kê tệp, bảng lưu trữ dạng file, cache bền vững, object stream, hàng đợi, topic và API payload có thể tồn tại qua lần triển khai. Ghi nhận phiên bản tạo dữ liệu, nơi lưu, thời gian lưu trữ và thành phần đang đọc dữ liệu.

### Bước 2: Thu thập ví dụ dữ liệu thật

Giữ các mẫu dữ liệu đại diện từ những phiên bản còn cần hỗ trợ. Loại bỏ thông tin nhạy cảm trước khi đưa fixture vào kho mã nguồn. Fixture nên bao gồm trường thiếu, giá trị rỗng, giá trị biên và các trường hợp lịch sử đã từng gây lỗi.

### Bước 3: Viết hợp đồng và ma trận tương thích

Với mỗi định dạng, ghi lại tên trường, kiểu, ý nghĩa, đơn vị, giá trị mặc định, quy tắc khi thiếu và phiên bản hỗ trợ. Nêu rõ bộ đọc nào phải đọc được dữ liệu của bộ ghi nào. Đừng chỉ dựa vào cấu trúc của lớp Java hiện tại để suy ra hợp đồng.

### Bước 4: Xây dựng bộ chuyển đổi tập trung

Đặt logic đọc định dạng cũ và chuyển đổi vào một lớp hoặc module chuyên trách. Chuyển dữ liệu lịch sử về một mô hình nội bộ ổn định, sau đó để nghiệp vụ làm việc với mô hình đó. Tránh rải các điều kiện `if (version == 1)` ở nhiều nơi trong ứng dụng.

### Bước 5: Triển khai theo thứ tự phù hợp

Đối với thông điệp, thường cần nâng cấp consumer trước khi producer phát dữ liệu mới. Đối với tệp, cần xác định thời điểm ngừng tạo định dạng cũ và thời điểm chuyển đổi dữ liệu. Đối với Java Serialization, cần chắc chắn lớp mới có thể đọc các luồng cũ hoặc đã có công cụ chuyển đổi riêng.

### Bước 6: Theo dõi sau di chuyển

Ghi nhận số bản ghi hoặc tệp đã chuyển đổi, số trường hợp thất bại, phiên bản nguồn và nguyên nhân lỗi. Giữ khả năng khôi phục khi dữ liệu mới không hợp lệ. Với thông điệp, theo dõi tỷ lệ giải mã lỗi, retry và dead-letter queue.

## 7. Kiểm thử tương thích

Kiểm thử chỉ bằng dữ liệu do phiên bản mới nhất tạo ra sẽ bỏ sót phần lớn lỗi migration. Nên kiểm thử theo ma trận phiên bản và lưu dữ liệu mẫu lâu dài.

### 7.1. Golden fixtures

Golden fixture là tệp hoặc thông điệp mẫu được tạo bởi phiên bản trước và được giữ làm dữ liệu đầu vào cố định cho kiểm thử. Khi thay đổi lớp hoặc schema, kiểm thử bộ đọc hiện tại với toàn bộ fixture còn trong thời hạn hỗ trợ.

Ví dụ, một bài kiểm thử có thể xác nhận rằng dữ liệu JSON phiên bản 1 được chuyển thành mô hình hiện tại với giá trị mặc định đúng:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

import org.junit.jupiter.api.Test;

class CustomerFileMigrationTest {
    @Test
    void readsVersion1FileWithDefaultEmail() throws Exception {
        Customer customer = CustomerFileReader.read(
                getClass().getResourceAsStream("/fixtures/customer-v1.json"));

        assertEquals("C-1042", customer.getId());
        assertEquals("Nguyen An", customer.getName());
        assertNull(customer.getEmail());
    }
}
```

`CustomerFileReader` và `Customer` là tên minh họa; trong dự án thực tế, fixture phải được tạo từ định dạng thật và kỳ vọng phải phản ánh chính sách dữ liệu đã thống nhất. Nếu `null` không phải trạng thái hợp lệ, bài kiểm thử cần xác nhận một giá trị mặc định hoặc lỗi dữ liệu rõ ràng.

### 7.2. Kiểm thử ma trận producer/consumer

Với thông điệp, kiểm thử các cặp phiên bản cần hỗ trợ: producer cũ với consumer mới, producer mới với consumer cũ, và cả hai cùng mới. Cần kiểm thử cả thông điệp hợp lệ, trường bị thiếu, trường có giá trị chưa biết và enum mới.

Contract test giúp kiểm tra rằng producer phát đúng schema đã công bố và consumer vẫn chấp nhận các payload thuộc phạm vi cam kết. Nếu dùng schema registry, kiểm tra chính sách tương thích ngay trong quy trình build hoặc phát hành.

### 7.3. Kiểm thử chuyển đổi và khôi phục

Ngoài việc đọc thành công, cần kiểm tra:

- Giá trị sau chuyển đổi giữ nguyên ý nghĩa nghiệp vụ.
- Đơn vị, múi giờ và độ chính xác số không bị thay đổi ngoài dự kiến.
- Dữ liệu không hợp lệ được báo lỗi rõ ràng và không làm mất bản gốc.
- Chạy lại migration không làm thay đổi thêm dữ liệu đã chuyển đổi.
- Tệp ghi mới có thể được bộ đọc mới đọc lại.
- Nếu có yêu cầu tương thích xuôi, bộ đọc cũ xử lý được phần dữ liệu mới theo chính sách đã công bố.

Với Java Serialization, hãy lưu ít nhất một luồng được tạo từ mỗi phiên bản lớp cần hỗ trợ. Không tạo fixture cũ bằng cách chạy lại mã mới, vì khi đó fixture không còn đại diện cho cấu trúc lịch sử.

## 8. Những lỗi thiết kế thường gặp

**Đổi tên trường rồi cho rằng dữ liệu cũ tự chuyển theo.** Trong Java Serialization, tên trường cũ và mới không tự ánh xạ cho nhau. Trong JSON hoặc CSV, consumer cũng cần quy tắc alias hoặc chuyển đổi rõ ràng.

**Thêm trường nhưng coi nó luôn có mặt.** Dữ liệu cũ không chứa trường mới. Consumer phải xác định giá trị mặc định hoặc xử lý trường hợp thiếu.

**Giữ nguyên kiểu nhưng đổi ý nghĩa.** Đổi đơn vị tiền tệ, múi giờ hoặc cách làm tròn vẫn là thay đổi hợp đồng. Hãy dùng trường mới hoặc phiên bản mới nếu không thể giữ ý nghĩa cũ.

**Dùng `serialVersionUID` như một công tắc sửa lỗi.** Đặt UID bằng nhau có thể vượt qua một bước kiểm tra nhưng không biến hai cấu trúc không tương thích thành tương thích. Cần hiểu quy tắc serialization và có kiểm thử bằng dữ liệu cũ.

**Chỉ kiểm thử dữ liệu mới.** Điều này không chứng minh ứng dụng có thể đọc dữ liệu đang tồn tại trong hệ thống. Hãy giữ fixture lịch sử và kiểm thử theo ma trận phiên bản.

**Xóa trường hoặc schema cũ quá sớm.** Hàng đợi, log sự kiện, bản sao lưu và tệp xuất có thể còn tồn tại lâu hơn thời gian triển khai. Chỉ ngừng hỗ trợ khi đã xác định hết vòng đời của dữ liệu cũ.

**Bỏ qua trường chưa biết một cách vô điều kiện.** Cách này có thể giúp consumer cũ không lỗi khi gặp trường mới, nhưng cũng có thể làm mất thông tin quan trọng. Chính sách bỏ qua phải phù hợp với nghiệp vụ và có quan sát lỗi.

## 9. Checklist trước khi phát hành thay đổi dữ liệu

- [ ] Đã xác định tất cả nơi tạo, lưu và đọc dữ liệu.
- [ ] Đã ghi rõ phiên bản định dạng và ma trận tương thích cần hỗ trợ.
- [ ] Trường mới có chính sách xử lý khi dữ liệu cũ không chứa trường đó.
- [ ] Không âm thầm đổi kiểu, đơn vị hoặc ý nghĩa trường hiện có.
- [ ] Có fixture được tạo từ các phiên bản trước còn cần hỗ trợ.
- [ ] Đã kiểm thử producer/consumer hoặc writer/reader theo thứ tự triển khai dự kiến.
- [ ] Quy trình migration có thể chạy lại và có cách khôi phục dữ liệu.
- [ ] Có log hoặc metric để phát hiện lỗi giải mã và dữ liệu không hợp lệ.
- [ ] Đã xác định thời điểm ngừng hỗ trợ định dạng hoặc schema cũ.
- [ ] Nếu dùng Java Serialization, đã đánh giá rủi ro giải tuần tự hóa và giới hạn kiểu được phép đọc.

## Kết luận

Tương thích dữ liệu cần được thiết kế như một phần của hợp đồng giữa các phiên bản ứng dụng. Với tệp, hãy quản lý encoding, cấu trúc và phiên bản định dạng; với Java Serialization, hiểu rõ `serialVersionUID`, quy tắc thay đổi lớp và cơ chế khôi phục trạng thái; với thông điệp, phối hợp schema và thứ tự triển khai producer/consumer. Khi có dữ liệu mẫu lịch sử, bộ chuyển đổi tập trung và kiểm thử theo ma trận phiên bản, việc nâng cấp Java sẽ ít phụ thuộc vào giả định rằng mọi dữ liệu trong hệ thống đều được tạo bởi mã mới nhất.
