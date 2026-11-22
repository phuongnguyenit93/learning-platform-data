# Không xem serialize rồi deserialize là cách sao chép mặc định cho mọi lớp

## 1. Phân biệt sao chép đối tượng và Java Serialization

Một kỹ thuật thường được gọi là "deep copy bằng serialization" là dùng `ObjectOutputStream` để chuyển một object sang dãy byte, sau đó dùng `ObjectInputStream` để đọc dãy byte ấy thành object. Quy trình khái niệm:

```text
Đối tượng gốc → ghi ObjectOutputStream → byte[]
byte[] → đọc ObjectInputStream → đối tượng khôi phục
```

Với một đồ thị gồm các object hỗ trợ Java Serialization và không có cơ chế thay thế đặc biệt, cách này *có thể* tạo ra những object mới chứa nhiều dữ liệu tương đương với bản gốc. Tuy nhiên, mục đích gốc của Java Object Serialization là biểu diễn và khôi phục trạng thái theo một **giao thức serialization**, không phải cung cấp hợp đồng sao chép mọi lớp.

Muốn gọi một thao tác là "copy" cần xác định rõ: bản mới có phải khác tham chiếu không, những trường nào được giữ, trường nào phải tách khỏi bản gốc, quan hệ dùng chung giữa các trường có được bảo toàn không, tài nguyên ngoài bộ nhớ có được dùng chung hay tạo lại, và constructor/invariant của lớp có được đáp ứng không.

**Kết luận:** serialize rồi deserialize không phải lựa chọn mặc định cho mọi lớp. Hãy xem nó là một kỹ thuật có nhiều điều kiện và giới hạn, không phải một hàm `deepCopy(Object)` tự động đúng trong mọi trường hợp.

## 2. Điều kiện Serializable áp dụng cho cả đồ thị

`java.io.Serializable` là một *marker interface*: không bắt lớp phải triển khai phương thức nào. Khi gọi `ObjectOutputStream.writeObject(root)`, bộ ghi có thể đi theo các trường tham chiếu của `root` để ghi những object trong đồ thị.

Nếu gặp một object không hỗ trợ Serializable qua một trường cần ghi, quá trình có thể ném `NotSerializableException`, ngay cả khi lớp `root` đã `implements Serializable`.

```java
import java.io.Serializable;

// Minh họa hai lớp, chưa phải chương trình độc lập.
final class Attachment {
    String location = "folder/item";
}
final class Report implements Serializable {
    private static final long serialVersionUID = 1L;
    Attachment attachment = new Attachment();
}
```

`Report` là Serializable, nhưng `Attachment` không phải. Việc serialize một `Report` chứa `attachment` theo quy tắc mặc định sẽ thất bại. Thêm `implements Serializable` cho lớp gốc không tự động làm những đối tượng được tham chiếu trở nên Serializable.

| Loại trạng thái | Hành vi điển hình khi serialize/deserialze |
| --- | --- |
| Trường nguyên thủy | Giá trị được ghi và khôi phục theo dạng serialized. |
| Trường tham chiếu bình thường | Đối tượng tham chiếu cần thỏa cơ chế serialization tương ứng. |
| Trường `transient` | Bị bỏ qua ở dạng ghi mặc định; khi đọc lại thường nhận giá trị mặc định nếu không có logic khôi phục khác. |
| Trường `static` | Không phải trạng thái instance; không tạo một bản copy static độc lập. |
| Tài nguyên bên ngoài | Socket, thread, stream, lock, kết nối, transaction... không tự được nhân bản đúng nghĩa nghiệp vụ. |

Dùng `transient` để tránh lỗi ghi **không đồng nghĩa** copy thành công. Nếu trường là cache có thể tính lại, việc mất nó có thể chấp nhận; nếu nó là dependency cần thiết để object hoạt động, bản khôi phục có thể thiếu trạng thái quan trọng.

Đối với lớp Serializable thông thường, deserialization **không gọi constructor của lớp đó như lệnh `new`**. Với một superclass không Serializable, Java có quy tắc gọi constructor không tham số có thể truy cập của superclass gần nhất không Serializable. Vì thế cách khôi phục trường và invariant không nhất thiết giống copy constructor.

## 3. Sao chép đồ thị: giữ tham chiếu lặp và chu trình

Serialization mặc định có cơ chế ghi nhận các object đã xuất hiện trong stream:

```text
Gốc:
Container
 ├─ first ──┐
 └─ second ─┴──> Node A ─next─> Node A

Khôi phục:
Container'
 ├─ first ──┐
 └─ second ─┴──> Node A' ─next─> Node A'
```

Trong một đồ thị Serializable thích hợp, `A'` là node khác `A` nhưng hai trường `first` và `second` của container mới vẫn trỏ **cùng A'**; chu trình `next` cũng có thể được khôi phục. Đây là ưu điểm kỹ thuật so với một hàm clone đệ quy ngây thơ làm mất alias hoặc lặp vô hạn.

Nhưng sao chép sâu theo nghiệp vụ không chỉ là "mọi object khác tham chiếu": có object cần tiếp tục dùng chung, có tài nguyên không được nhân bản, có ID phải giữ hoặc phải cấp mới. Hơn nữa, các lớp có `readResolve`, `writeReplace`, `writeObject`, `readObject` hoặc `Externalizable` có thể chủ động thay đổi dạng ghi/đọc hoặc đối tượng kết quả. `enum` cũng có ngữ nghĩa đặc biệt về instance. Không thể tuyên bố mọi lần round-trip đều trả về một object độc lập mới.

## 4. Ví dụ Java 17 hoàn chỉnh: những gì được bảo toàn, những gì mất

Tạo tệp `SerializationCopyDemo.java`:

```java
import java.io.*;
import java.util.ArrayList;
import java.util.List;

public class SerializationCopyDemo {
    static final class Node implements Serializable {
        @Serial
        private static final long serialVersionUID = 1L;

        String title;
        List<String> tags = new ArrayList<>();
        Node next;
        transient String cache = "ready";

        Node(String title) {
            this.title = title;
        }
    }

    static final class Pair implements Serializable {
        @Serial
        private static final long serialVersionUID = 1L;

        Node left;
        Node right;

        Pair(Node value) {
            left = value;
            right = value;
        }
    }

    static Pair roundTrip(Pair value)
            throws IOException, ClassNotFoundException {
        byte[] data;
        try (ByteArrayOutputStream bytes = new ByteArrayOutputStream();
             ObjectOutputStream out = new ObjectOutputStream(bytes)) {
            out.writeObject(value);
            out.flush();
            data = bytes.toByteArray();
        }
        try (ObjectInputStream in = new ObjectInputStream(
                new ByteArrayInputStream(data))) {
            return (Pair) in.readObject();
        }
    }

    public static void main(String[] args) throws Exception {
        Node n = new Node("Java");
        n.tags.add("core");
        n.next = n;

        Pair original = new Pair(n);
        Pair copied = roundTrip(original);

        System.out.println("different root: "
                + (original != copied));
        System.out.println("different child: "
                + (original.left != copied.left));
        System.out.println("alias kept: "
                + (copied.left == copied.right));
        System.out.println("cycle kept: "
                + (copied.left.next == copied.left));
        System.out.println("original cache: " + original.left.cache);
        System.out.println("copied cache: " + copied.left.cache);

        copied.left.tags.add("copy");
        System.out.println("original tags: " + original.left.tags);
        System.out.println("copied tags: " + copied.left.tags);
    }
}
```

Chạy với JDK 17 trở lên:

```bash
javac SerializationCopyDemo.java
java SerializationCopyDemo
```

Stdout:

```text
different root: true
different child: true
alias kept: true
cycle kept: true
original cache: ready
copied cache: null
original tags: [core]
copied tags: [core, copy]
```

Giải thích: `Pair` và `Node` ở đồ thị khôi phục là các instance khác đồ thị gốc. Tuy nhiên, cả hai trường `left` và `right` ở bản mới vẫn dùng chung một node mới, và `next` tạo vòng tới chính node đó. `tags` trong đồ thị mới độc lập nên có thể thêm phần tử mà không sửa `tags` gốc.

Trường `cache` là `transient`, vì vậy không có trong dạng ghi mặc định. Field initializer `"ready"` của lớp Serializable không chạy như lúc tạo instance thông thường trong quá trình đọc, nên bản copy có `cache == null`. Một object trông giống bản copy "sâu" vẫn có thể **thiếu dữ liệu**.

Chương trình chỉ deserialize dãy byte tự nó vừa tạo ra từ các lớp đã biết. Không sử dụng đoạn mã này như một API tiếp nhận dữ liệu serialized từ nguồn không tin cậy.

## 5. Một trường không Serializable gây lỗi; `transient` thay đổi ý nghĩa bản sao

Đặt thêm vào chương trình minh họa khác:

```java
class NativeResource {
    String name = "R1";
}

class Job implements java.io.Serializable {
    private static final long serialVersionUID = 1L;
    NativeResource resource = new NativeResource();
}
```

Hai lớp trên minh họa, chưa có `main`. `Job` implements Serializable nhưng `resource` giữ một `NativeResource` không Serializable. Nếu ghi `new Job()` qua `ObjectOutputStream.writeObject`, việc ghi sẽ ném `NotSerializableException`.

Có thể thử thay bằng:

```java
transient NativeResource resource = new NativeResource();
```

Dòng trên là khai báo trường minh họa trong `Job`. Khi đó việc ghi mặc định sẽ bỏ trường `resource`. Tuy nhiên, **bản đọc lại không còn object `resource`**, và constructor của `Job` không tự chạy lại để tạo `new NativeResource()`. Nếu các phương thức `Job` cần `resource`, chúng có nguy cơ gặp `NullPointerException` hoặc vi phạm invariant, trừ khi lớp có quy tắc khôi phục riêng được thiết kế cẩn thận.

Một lựa chọn rõ ràng hơn có thể là copy constructor, factory tạo `NativeResource` độc lập khi cần, hoặc cấm copy khi resource không có ngữ nghĩa nhân bản an toàn. Không nên dùng `transient` như mẹo làm cho mọi lớp ghi được.

## 6. Vì sao không thể mặc định gọi đây là deep copy?

Cần phân biệt **sao chép trạng thái Serializable** và **sao chép theo hợp đồng nghiệp vụ**.

1. **Đồ thị có thể không Serializable hoàn chỉnh.** Một phần tử lồng sâu không Serializable đủ để làm luồng ghi thất bại.
2. **Có trường không được ghi.** `transient` mất dữ liệu theo mặc định; `static` không được sao chép theo từng instance.
3. **Đối tượng có logic serialization riêng.** `readResolve` có thể trả về instance dùng chung, `readObject` có thể khôi phục hoặc thay đổi trạng thái theo logic lớp, các hook có thể ảnh hưởng cách khôi phục.
4. **Tài nguyên không đơn thuần là byte.** File descriptor, kết nối, luồng xử lý, lock và handle bên ngoài JVM cần chính sách vòng đời, không thể clone bằng cách khôi phục các trường Java.
5. **Bất biến constructor có thể khác.** Các bước validation, đăng ký vào registry, cấp ID, khởi tạo lock hoặc cache thường được thực hiện trong constructor/factory; serializer không mặc định lặp lại những bước đó.
6. **Độc lập và chia sẻ là quyết định nghiệp vụ.** Một bản sao có thể phải tạo riêng danh sách nhưng giữ chung object immutable; hoặc phải tách con trỏ về parent và giữ quan hệ alias. Kỹ thuật serializer không tự hiểu ý nghĩa của từng trường.
7. **Trạng thái có thể bị thay đổi đồng thời.** Nếu luồng khác sửa object khi đang ghi, ứng dụng phải bảo đảm snapshot nhất quán; serialization không tự thay thế đồng bộ hóa ở cấp nghiệp vụ.
8. **Định dạng có thể không tương thích về sau.** Thay đổi cấu trúc class, serial form hoặc serialVersionUID có thể khiến khôi phục thất bại hoặc tạo dữ liệu không còn hợp lệ.

Đừng chỉ kiểm thử `copy != original`. Một phép copy đáng tin cần thử chỉnh sửa mutable field ở bản mới có ảnh hưởng tới bản cũ hay không, các quan hệ alias và chu trình, toàn bộ invariant và các tài nguyên bắt buộc sau copy.

## 7. So sánh với `clone()`, copy constructor và factory

| Cách sao chép | Đặc điểm | Phù hợp khi |
| --- | --- | --- |
| `super.clone()` đi tới `Object.clone()` | Sao chép nông trường instance; tham chiếu object con vẫn dùng chung. | API clone đã có hợp đồng rõ; có thể tự xử lý trường mutable. |
| Copy constructor `new Type(source)` | Constructor chủ động chọn trường cần sao chép, có thể gán trường `final` mới và xác nhận invariant. | Cấu trúc dữ liệu tương đối rõ, cần chính sách copy minh bạch. |
| Factory `Type.copyOf(source)` | Có thể tạo snapshot, object mới hoặc tái dùng immutable object theo hợp đồng. | Muốn API dễ tiến hóa và kiểm soát trạng thái. |
| Serialize → deserialize | Ghi/đọc đồ thị theo quy tắc Java Serialization, có thể giữ alias và chu trình. | Chỉ khi đồ thị phù hợp, hệ thống thực sự cần serial form, nguồn dữ liệu được kiểm soát và chi phí được chấp nhận. |
| Dữ liệu immutable | Có thể chia sẻ an toàn mà không cần deep clone. | Tất cả thành phần liên quan thực sự bất biến. |

Với những trường hợp đơn giản, copy constructor thường dễ đọc hơn:

```java
import java.util.ArrayList;
import java.util.List;

final class Profile {
    private final String name;
    private final List<String> labels;

    Profile(String name, List<String> labels) {
        this.name = name;
        this.labels = new ArrayList<>(labels);
    }

    Profile(Profile source) {
        this(source.name, source.labels);
    }
}
```

Đây là khai báo lớp, không có `main`. Constructor sao chép tạo **danh sách mới**; các phần tử là `String` bất biến nên có thể được chia sẻ. Nếu `labels` chứa object mutable, `new ArrayList<>(labels)` vẫn chỉ là copy nông **các phần tử**, cần thêm chính sách tách object con.

Nếu bản sao cần tạo ID mới, đóng/mở tài nguyên khác, bỏ cache, hoặc thay thông tin môi trường thì nên thể hiện rõ trong constructor/factory. Những quy tắc đó không nên bị giấu sau một utility serialize/deserialize tổng quát.

## 8. Hiệu năng, tương thích và bảo mật

### Chi phí thực thi

Một round-trip yêu cầu đi qua đồ thị, mã hóa byte, cấp phát buffer và tạo lại object từ byte. Điều này có thể tiêu tốn CPU, bộ nhớ tạm, gây áp lực thu gom rác và chạy các callback serialization. Không thể suy luận nó **luôn** chậm hơn mọi copy constructor trong mọi tình huống, nhưng rõ ràng phải thực hiện những bước bổ sung ngoài sao chép trực tiếp các dữ liệu cần thiết. Với thao tác copy thường xuyên hoặc đồ thị lớn, nên cân nhắc thiết kế khác và đo bằng benchmark phù hợp.

### Tương thích phiên bản

`serialVersionUID` hỗ trợ cơ chế kiểm tra tương thích khi đọc dữ liệu đã ghi bởi các phiên bản class khác nhau. Nó **không bảo đảm** mọi thay đổi field, kế thừa hoặc bất biến nghiệp vụ đều tương thích. Thay đổi không tương thích có thể dẫn tới `InvalidClassException` hoặc khôi phục trạng thái thiếu/sai so với yêu cầu mới.

Nếu cần một định dạng lưu trữ hay trao đổi lâu dài, hãy thiết kế DTO/schema, versioning, validation và chiến lược migration phù hợp. Đó là yêu cầu khác với việc muốn tạo bản sao trong bộ nhớ.

### An toàn dữ liệu

`ObjectInputStream` không nên được dùng để xử lý dữ liệu Java serialized từ **nguồn không tin cậy**. Cơ chế khôi phục có thể kích hoạt logic của các class có trong hệ thống, và dạng byte này không tự có mã hóa, xác thực hay validation nghiệp vụ. Khi phải duy trì Java Serialization trong hệ thống cũ, cần giới hạn kiểu/kích thước và áp dụng các biện pháp bảo vệ thích hợp, chẳng hạn object input filtering, kiểm soát nguồn và kiểm tra dữ liệu sau khi đọc. Các biện pháp này không biến mọi đầu vào bên ngoài thành an toàn.

**Không thêm `implements Serializable` hàng loạt chỉ để có hàm copy tiện.** Điều đó mở rộng trách nhiệm về định dạng, tương thích và bề mặt xử lý dữ liệu serialized.

## 9. Thiết kế hợp đồng copy đúng cho object model

Trước khi quyết định cách làm, trả lời:

- Bản copy phải có **danh tính mới** hay được phép trả chính object immutable cũ?
- Những trường nào là **giá trị cốt lõi**, trường nào chỉ là cache/metadata/tài nguyên phụ?
- Cần giữ nguyên ID nghiệp vụ hay cấp ID mới?
- Các trường `List`, `Map`, mảng, object con mutable có cần độc lập không? Độc lập đến độ sâu nào?
- Hai trường đang cùng trỏ một node có phải tiếp tục cùng trỏ **một node mới** trong bản copy không?
- Có tham chiếu vòng không? Nếu tự copy đồ thị, nên dùng bảng ánh xạ theo danh tính từ node gốc sang node bản sao để tránh lặp và giữ quan hệ chia sẻ.
- Có trường `final`, invariant constructor, lock hoặc resource cần tạo lại bằng factory không?
- Object có thể bị sửa bởi luồng khác khi copy không? Có cơ chế snapshot nhất quán chưa?
- Các trường tham gia `equals`/`hashCode` có yêu cầu bất biến khi đối tượng dùng làm khóa trong map/set không?

Sau đó kiểm thử trên bản sao: kiểm tra giá trị, sửa dữ liệu mutable ở một phía, kiểm tra alias và chu trình, xác minh invariant, tài nguyên và việc đóng/mở đúng ownership.

**Gợi ý thực hành:** dữ liệu nhỏ và dễ hiểu thường phù hợp với copy constructor/factory; object value immutable ít khi cần copy sâu; đồ thị mutable phức tạp cần hàm sao chép có chính sách, có thể dùng bản đồ object theo identity. Serialization có thể phù hợp nếu định dạng và ngữ nghĩa của nó đã là yêu cầu thực tế, chứ không phải cách mặc định.

## 10. Các nhầm lẫn thường gặp và tự kiểm tra

| Nhầm lẫn | Vì sao không đúng |
| --- | --- |
| Lớp gốc Serializable thì mọi trường đều copy được. | Đồ thị có thể chứa object không Serializable. |
| Dùng `transient` thì copy tương đương bản gốc. | Trường bị bỏ qua, có thể phá invariant. |
| Deserialize luôn gọi constructor của lớp Serializable. | Cơ chế khôi phục không giống `new` thông thường. |
| Mọi reference trong bản sao đều độc lập. | Alias và chu trình có thể được bảo toàn; một số loại có logic thay thế instance. |
| Serialization tự copy socket/lock/connection. | Tài nguyên cần hợp đồng vòng đời riêng. |
| Có `serialVersionUID` là tương thích mọi phiên bản. | Class vẫn có thể thay đổi không tương thích hoặc sai ý nghĩa dữ liệu. |
| Deserialize byte bất kỳ là thao tác vô hại. | Dữ liệu serialized không tin cậy phải tránh hoặc được xử lý theo chính sách bảo vệ nghiêm ngặt. |
| Deep copy nghĩa là sao chép mọi thứ. | Deep copy phải được định nghĩa theo dữ liệu nào cần độc lập và những quan hệ nào cần giữ. |

**Câu hỏi tự kiểm tra:**

1. Một `Report implements Serializable` chứa trường `Attachment` không Serializable sẽ có vấn đề gì khi `writeObject`?
2. Vì sao `transient` có thể làm thao tác ghi thành công nhưng bản đọc lại thiếu dữ liệu?
3. Nếu hai trường cùng trỏ tới một node, bản serialize/deserialize mặc định có nhất thiết tách hai trường thành hai node khác nhau không?
4. Vì sao cần kiểm tra cả quan hệ alias và chu trình khi sao chép một đồ thị?
5. Tại sao không nên copy `Socket`, `Thread` hay một kết nối cơ sở dữ liệu bằng serialization?
6. Copy constructor mang lại lợi ích gì khi lớp có nhiều trường `final` hoặc logic validation quan trọng?
7. Khi nào chia sẻ một object immutable tốt hơn tạo bản sao?
8. Vì sao không dùng `ObjectInputStream` tùy tiện với byte do bên ngoài cung cấp?
9. Sau một bản copy, có nên tự động giữ nguyên một ID phải là duy nhất trong hệ thống không?
10. Cần những phép thử nào để biết một bản sao thực sự độc lập với những trường mutable quan trọng?

**Ghi nhớ:** Java Serialization có thể ghi và khôi phục một **đồ thị Serializable**, nhưng không phải một hợp đồng sao chép mặc định cho mọi lớp. `NotSerializableException`, trường `transient`, cơ chế custom serialization, tài nguyên ngoại vi, tương thích phiên bản, chi phí và bảo mật đều là lý do phải **chọn chính sách copy trước** rồi mới chọn kỹ thuật. Với nhiều lớp ứng dụng, copy constructor, factory hoặc thiết kế immutable rõ ràng và dễ kiểm soát hơn.