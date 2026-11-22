# \`@Serial\` trong Java: kiểm tra các thành phần phục vụ tuần tự hóa

## 1. \`@Serial\` giải quyết vấn đề gì?

Khi một lớp Java tham gia **object serialization**, một số field và method có **tên, kiểu và phạm vi truy cập đặc biệt** để cơ chế tuần tự hóa nhận diện. Chẳng hạn:

- \`serialVersionUID\` xác định mã phiên bản serialization của lớp.
- \`writeObject(ObjectOutputStream)\` và \`readObject(ObjectInputStream)\` cho phép lớp tùy biến cách ghi/đọc trạng thái.
- \`readResolve()\` và \`writeReplace()\` hỗ trợ thay đối tượng trong quá trình đọc/ghi.

Các khai báo này **không phải method override từ \`Serializable\`**. Interface \`java.io.Serializable\` không khai báo method nào; Java serialization nhận ra các thành phần đặc biệt thông qua quy ước tên, kiểu, modifiers và ngữ cảnh của lớp. Một lỗi đánh máy như \`writeObjects\` thay vì \`writeObject\` có thể khiến chương trình vẫn biên dịch, nhưng cơ chế serialization bỏ qua method định viết.

**\`java.io.Serial\`** (có từ **Java 14**) là annotation chuẩn dùng để **đánh dấu các khai báo phục vụ serialization**, tạo cơ hội để trình biên dịch và công cụ phân tích kiểm tra xem khai báo có hợp lệ và có tác dụng trong ngữ cảnh đó hay không.

Ví dụ:

~~~java
import java.io.Serial;
import java.io.Serializable;

final class AccountSnapshot implements Serializable {
    @Serial
    private static final long serialVersionUID = 1L;
}
~~~

Ở đây:

1. \`implements Serializable\` cho biết lớp tham gia cơ chế object serialization mặc định của Java.
2. \`serialVersionUID\` là field đặc biệt có ý nghĩa khi serialize/deserialize phiên bản lớp.
3. \`@Serial\` mô tả **vai trò của field với compiler/tooling**. Annotation này **không phải** thứ làm lớp serializable, cũng không tự sinh UID.

\`@Serial\` có thể xem là gần với \`@Override\` ở mục đích **giúp phát hiện sai khai báo**. Tuy nhiên, hai annotation kiểm tra **hai hợp đồng khác nhau**: \`@Override\` kiểm tra method override/implement; \`@Serial\` đánh dấu thành phần serialization đặc biệt, vốn thường không phải override.

## 2. Đặc điểm kỹ thuật của annotation

Khai báo API chuẩn có các metadata sau:

~~~java
@Target({ElementType.METHOD, ElementType.FIELD})
@Retention(RetentionPolicy.SOURCE)
public @interface Serial {
}
~~~

Đây là **hình thức rút gọn để giải thích metadata**, không phải source khai báo thật của JDK và không dùng để định nghĩa lại \`java.io.Serial\`.

| Thuộc tính | Ý nghĩa |
| --- | --- |
| Package | \`java.io.Serial\` |
| Bắt đầu hỗ trợ | Java 14 |
| \`@Target\` | **METHOD** hoặc **FIELD** |
| \`@Retention\` | **SOURCE** |
| Annotation elements | Không có; viết \`@Serial\`, không cần tham số |
| Công dụng | Đánh dấu thành phần đặc biệt mà Java Object Serialization Specification định nghĩa; hỗ trợ kiểm tra ở thời điểm biên dịch |

Do retention là **SOURCE**, \`@Serial\` không được lưu trong \`.class\` cho chương trình đọc bằng runtime reflection. **Không** viết logic runtime kiểu \`method.isAnnotationPresent(Serial.class)\` rồi chờ kết quả \`true\`; nó không phải cơ chế đăng ký hay bật/tắt serialization.

Văn bản API nói compiler **được khuyến khích** kiểm tra và cảnh báo khi \`@Serial\` gắn vào khai báo không phù hợp; mức hỗ trợ và loại cảnh báo có thể khác theo compiler/JDK. Vì vậy, **đừng coi việc không thấy warning là bằng chứng mọi hook đã đúng**. Hãy kết hợp code review, test round-trip và kiểm thử hành vi tùy biến.

## 3. Những thành phần nào được phép dùng \`@Serial\`?

Theo hợp đồng của \`java.io.Serial\`, có **hai field** và **năm method** liên quan đến serialization. Không gắn annotation này lên bất kỳ field/method nào chỉ vì “muốn nó được serialize”.

### 3.1. Hai field đặc biệt

**(1) \`serialVersionUID\`**

~~~java
@Serial
private static final long serialVersionUID = 1L;
~~~

- Tên phải là \`serialVersionUID\`, kiểu là \`long\`, và phải có \`static final\`; khuyến nghị khai báo \`private\`.
- Object serialization đối chiếu UID khi đọc để kiểm tra tính tương thích của class descriptor. Không phù hợp có thể dẫn đến \`InvalidClassException\`.
- Annotation chỉ giúp khai báo rõ mục đích và mở ra khả năng kiểm tra; nó **không chọn giá trị UID, không quản lý phiên bản, không bảo đảm thay đổi cấu trúc class tương thích**.
- Nếu không khai báo UID, cơ chế Java có thể tự tính UID mặc định từ mô tả lớp; cách này dễ bị ảnh hưởng bởi thay đổi class. Với lớp serializable thông thường, nên khai báo UID một cách có chủ ý.

**(2) \`serialPersistentFields\`**

~~~java
@Serial
private static final java.io.ObjectStreamField[] serialPersistentFields = {
    new java.io.ObjectStreamField("id", long.class)
};
~~~

Đây là khai báo **minh họa thành phần đặc biệt**, đặt **bên trong một lớp \`Serializable\`**, không phải chương trình chạy độc lập. Nó mô tả tập field đưa vào serial form thay cho danh sách field mặc định. Khi xây serialization tùy biến, code đọc/ghi phải xử lý nhất quán serial form đã định nghĩa; không nên thêm \`serialPersistentFields\` khi chưa hiểu tác dụng lên dữ liệu được lưu.

Đối với \`@Serial\`, khai báo chuẩn của cả hai field là **\`private static final\`** với tên/kiểu đúng như trên.

### 3.2. Năm method đặc biệt

Bảng dưới đây ghi **mẫu khai báo chuẩn**; các \`throws\` mô tả ngoại lệ có thể phát sinh. Java không tính \`throws\` là một phần của chữ ký method khi overload.

| Method | Mẫu khai báo chuẩn | Vai trò |
| --- | --- | --- |
| \`writeObject\` | \`private void writeObject(ObjectOutputStream out) throws IOException\` | Tùy biến ghi trạng thái của lớp vào stream |
| \`readObject\` | \`private void readObject(ObjectInputStream in) throws IOException, ClassNotFoundException\` | Tùy biến đọc/khôi phục trạng thái của lớp từ stream |
| \`readObjectNoData\` | \`private void readObjectNoData() throws ObjectStreamException\` | Khởi tạo trạng thái khi stream không chứa dữ liệu cho lớp này trong một số tình huống tiến hóa class hierarchy |
| \`writeReplace\` | \`Object writeReplace() throws ObjectStreamException\` | Chỉ định object thay thế khi ghi |
| \`readResolve\` | \`Object readResolve() throws ObjectStreamException\` | Chỉ định object thay thế sau khi đọc |

Với **ba method đầu**, \`private\` cùng tên, kiểu trả về và danh sách tham số chính xác là điểm quan trọng. Hai method \`writeReplace\` và \`readResolve\` có thể dùng các mức truy cập khác nhau theo quy tắc của đặc tả; khả năng được truy cập/kế thừa còn phụ thuộc Java accessibility. \`Object\` là kiểu trả về trong mẫu đặc tả.

Ví dụ một lớp serializable có hook ghi/đọc:

~~~java
@Serial
private void writeObject(ObjectOutputStream out) throws IOException {
    out.defaultWriteObject();
}

@Serial
private void readObject(ObjectInputStream in)
        throws IOException, ClassNotFoundException {
    in.defaultReadObject();
}
~~~

Ở đoạn này, \`ObjectOutputStream\`, \`ObjectInputStream\` và \`IOException\` nằm trong \`java.io\`; hai method được đặt **bên trong lớp implements \`Serializable\`**. Đây là **đoạn trích**, không phải file Java hoàn chỉnh. \`defaultWriteObject()\`/\`defaultReadObject()\` sử dụng cơ chế xử lý field mặc định cho phần trạng thái tương ứng của lớp. Nếu ghi thêm dữ liệu tùy biến, phải đọc lại **đúng thứ tự và định dạng**.

Với \`readObjectNoData\`, chỉ dùng khi có yêu cầu khôi phục invariant trong trường hợp dữ liệu của class không hiện diện trong stream. Với \`writeReplace\`/\`readResolve\`, nên hiểu rõ hệ quả về identity, kiểu trả về và vòng đời object trước khi dùng chúng để thay thế instance.

## 4. Ví dụ hoàn chỉnh: \`@Serial\` với serialize/deserialize thực tế

Giả sử cần lưu \`Member\` gồm tên và ghi chú kiểm toán. Field \`auditNote\` được đánh dấu \`transient\`, nên **không đi vào phần trạng thái mặc định**. Ta chọn ghi/đọc thủ công field này bằng hai hook có \`@Serial\` để minh họa hành vi.

Tạo file **\`SerialDemo.java\`**:

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.Serial;
import java.io.Serializable;

final class Member implements Serializable {
    @Serial
    private static final long serialVersionUID = 1L;

    private String name;
    private transient String auditNote;

    Member(String name, String auditNote) {
        this.name = name;
        this.auditNote = auditNote;
    }

    @Serial
    private void writeObject(ObjectOutputStream out) throws IOException {
        out.defaultWriteObject();
        out.writeUTF(auditNote);
    }

    @Serial
    private void readObject(ObjectInputStream in)
            throws IOException, ClassNotFoundException {
        in.defaultReadObject();
        auditNote = in.readUTF();
    }

    String display() {
        return name + " | audit=" + auditNote;
    }
}

public class SerialDemo {
    public static void main(String[] args) throws Exception {
        Member original = new Member("Lan", "created");
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (ObjectOutputStream out = new ObjectOutputStream(bytes)) {
            out.writeObject(original);
        }

        Member restored;
        try (ObjectInputStream in = new ObjectInputStream(
                new ByteArrayInputStream(bytes.toByteArray()))) {
            restored = (Member) in.readObject();
        }

        System.out.println("Before: " + original.display());
        System.out.println("After : " + restored.display());
    }
}
~~~

Đứng ở thư mục chứa file, dùng JDK 17 trở lên:

~~~bash
javac --release 17 -Xlint:serial -encoding UTF-8 SerialDemo.java
java SerialDemo
~~~

**Stdout** (đã kiểm chứng với JDK 21, biên dịch bằng \`--release 17\`):

~~~text
Before: Lan | audit=created
After : Lan | audit=created
~~~

Diễn giải cụ thể:

1. **Lớp được serialize vì implements \`Serializable\`**. \`@Serial\` giúp trình bày rõ ba khai báo đặc biệt, nhưng không biến \`Member\` thành serializable.
2. **\`writeObject\`** được serialization gọi theo quy ước hợp lệ. Nó ghi phần mặc định gồm \`name\`; sau đó ghi thêm \`auditNote\` bằng \`writeUTF\`.
3. **\`readObject\`** nhận lại phần mặc định qua \`defaultReadObject()\`, rồi đọc phần bổ sung bằng \`readUTF()\`. Tính đối xứng của thứ tự ghi/đọc là điều khiến kết quả đúng.
4. **\`serialVersionUID = 1L\`** khai báo định danh phiên bản cho serial form của lớp. Không đổi UID một cách tùy tiện nếu các dữ liệu cũ vẫn phải đọc được, nhưng cũng **không được** xem việc giữ nguyên UID là bảo đảm tương thích với mọi thay đổi lớp.
5. Ví dụ chỉ đọc lại stream **do chính chương trình tạo ra**. Đây không phải khuyến nghị dùng Java native deserialization cho dữ liệu không đáng tin cậy.

Nếu bỏ hai hook này, \`name\` vẫn thuộc trạng thái mặc định của \`Member\`, còn \`auditNote\` là \`transient\` nên sẽ trở thành \`null\` sau khi restore. Trong ví dụ thực tế, quyết định có ghi một trường nhạy cảm hoặc tạm thời vào stream phải dựa trên yêu cầu bảo mật và serial form, không dựa vào việc có \`@Serial\` hay không.

### Vì sao \`@Serial\` không thay thế test?

Thử tưởng tượng một người sửa:

~~~java
@Serial
private void writeObjects(ObjectOutputStream out) throws IOException {
    out.defaultWriteObject();
}
~~~

Đây là **đoạn minh họa lỗi**, không phải method sẽ được serializer công nhận: tên \`writeObjects\` khác \`writeObject\`. Annotation \`@Serial\` cho thấy ý định nhưng **không sửa sai tên**. Tùy compiler, có thể nhận được warning cho annotation đặt sai; không được mặc định rằng mọi JDK/thiết lập lint sẽ cảnh báo. Nếu code dựa vào hook này, cần test kiểm chứng **hook thực sự chạy** và dữ liệu round-trip đúng.

Trên một số phiên bản \`javac\`, \`-Xlint:serial\` có thể báo các vấn đề như thiếu \`serialVersionUID\`. Cờ lint hữu ích nhưng không phải bộ chứng minh rằng tất cả các special serialization method đều có hiệu lực.

## 5. Ngữ cảnh nào khiến \`@Serial\` không phù hợp?

### 5.1. Class không implements \`Serializable\`

~~~java
import java.io.Serial;

final class PlainDto {
    @Serial
    private static final long serialVersionUID = 1L;
}
~~~

Đây là **ví dụ dùng sai về ngữ nghĩa**: field nhìn có vẻ giống \`serialVersionUID\`, nhưng lớp không tham gia hợp đồng serialization tương ứng. Gắn annotation không làm lớp tự trở thành \`Serializable\`. Nếu không có nhu cầu Java native serialization, không cần UID hay \`@Serial\` chỉ để “phòng xa”.

### 5.2. Method trông giống hook nhưng sai hình thức

Các sai khác cần phát hiện:

- \`public void writeObject(ObjectOutputStream out)\`: hook \`writeObject\` của ordinary Serializable class phải là **private**.
- \`private void writeObject(String text)\`: tham số không phải \`ObjectOutputStream\`.
- \`private static void readObject(ObjectInputStream in)\`: static không phù hợp cho hook khôi phục state của instance.
- \`private void readObjects(ObjectInputStream in)\`: sai tên.
- \`@Serial\` trên một method nghiệp vụ bất kỳ như \`saveToDatabase()\`: method này không thuộc nhóm serialization hooks.

Java reflection hay serializer không suy từ annotation để biến những method trên thành hook tương ứng. Để phát hiện, hãy kiểm tra trực tiếp khai báo, dùng tooling phù hợp và có test hành vi.

### 5.3. \`Externalizable\`: hợp đồng serialization khác

\`Externalizable\` **extends \`Serializable\`**, nhưng dùng hai method công khai do interface định nghĩa: \`writeExternal(ObjectOutput)\` và \`readExternal(ObjectInput)\`. Không gắn \`@Serial\` cho chúng; chúng là **method implements của interface**, và \`@Override\` mới là annotation liên quan.

Trong lớp \`Externalizable\`, các khai báo \`writeObject\`, \`readObject\`, \`readObjectNoData\` và \`serialPersistentFields\` **không được serialization sử dụng như ở ordinary Serializable class**; gắn \`@Serial\` lên chúng là sai ngữ cảnh theo tài liệu API. \`serialVersionUID\` và các replacement hooks có những quy tắc riêng còn phù hợp trong ngữ cảnh nhất định. Đừng suy rằng mọi thành phần trong danh sách ở mục 3 đều hữu hiệu chỉ vì \`Externalizable\` là một subtype của \`Serializable\`.

### 5.4. \`enum\` và \`record\`

- **Enum** có cơ chế serialization đặc thù: UID được định nghĩa là \`0L\`, các special methods nói trên không được sử dụng như lớp thông thường. Gắn \`@Serial\` vào method/field bị bỏ qua không có ý nghĩa.
- **Serializable record** có quy tắc serialization riêng: các special customization methods được nêu trong \`Serializable\` docs không hoạt động như ở ordinary Serializable class. Không cố sao chép mọi hook của class thông thường vào record rồi kỳ vọng serialization gọi chúng.

Khi đối tượng là enum/record, nên đọc quy tắc cụ thể của loại đó trước khi tạo custom serialization form.

## 6. \`@Serial\` không giống các thành phần dễ nhầm

| Thành phần | Chức năng | Khác với \`@Serial\` |
| --- | --- | --- |
| \`Serializable\` | Marker interface cho cơ chế native object serialization | Quy định kiểu tham gia serialization; \`@Serial\` chỉ gắn vào field/method đặc biệt |
| \`serialVersionUID\` | Field version identifier được serializer sử dụng | Là dữ liệu/khai báo thật; \`@Serial\` đánh dấu nó |
| \`@Override\` | Kiểm tra hợp đồng ghi đè/triển khai method | \`writeObject\` và \`readObject\` là special hooks, không phải methods của \`Serializable\` để override |
| \`transient\` | Loại field khỏi trạng thái được serialize **mặc định** | Tác động đến xử lý field; không phải annotation kiểm tra |
| JavaDoc tag \`@serial\` | Tài liệu hóa serializable field/serialized form qua Javadoc | **Chữ thường**, nằm trong JavaDoc comment; khác annotation \`@Serial\` chữ hoa |
| \`@Serial\` | Metadata SOURCE để kiểm tra field/method serialization | Không điều khiển việc ghi byte, không thay UID và không thay code hook |

Một câu hỏi thường gặp: nếu \`Serializable\` là marker interface, vì sao ta không gọi \`writeObject\` trực tiếp qua interface này? Bởi \`Serializable\` **không định nghĩa API method**. Cơ chế \`ObjectOutputStream\` tự xử lý đối tượng và tìm các special hooks theo quy ước của serialization. Việc khai báo \`@Serial\` không bổ sung method vào interface.

## 7. Hướng dẫn áp dụng khi bảo trì code

Trước khi gắn \`@Serial\` lên một lớp:

1. **Xác minh nhu cầu serialize:** lớp thực sự implements \`Serializable\` hoặc có hợp đồng serialization tương ứng. Không thêm vì class là DTO, entity hay bean một cách máy móc.
2. **Chỉ đánh dấu đúng các thành phần đặc biệt:** tối đa hai loại field và năm loại method nêu ở mục 3; kiểm tra tên, modifiers, kiểu trả về, tham số và ngữ cảnh class.
3. **Kiểm tra khả năng tương thích dữ liệu:** UID, serial form và những field mới/bị đổi; thử đọc dữ liệu được tạo bằng phiên bản cũ khi ứng dụng có cam kết tương thích.
4. **Kiểm thử hành vi:** một lần serialize/deserialize thành công là bước đầu; nếu có hook tùy biến, kiểm tra data, invariant và đường đi của hook. Với dạng ghi/đọc riêng, thứ tự field và ngoại lệ phải được xử lý tương ứng.
5. **Bảo vệ đầu vào không đáng tin:** native Java deserialization của stream tùy ý có rủi ro bảo mật; tránh deserialize dữ liệu từ nguồn không tin cậy. Nếu bắt buộc hỗ trợ, cần thiết kế giới hạn và bộ lọc deserialize phù hợp (ví dụ \`ObjectInputFilter\`) và kiểm soát kiểu dữ liệu được chấp nhận.

### Các lỗi thường gặp

**Tưởng \`@Serial\` tự bật serialization.** Lớp phải có hợp đồng serialization và quá trình ghi/đọc thực sự được gọi; annotation không tạo khả năng đó.

**Dùng \`@Serial\` như \`@Override\`.** \`@Override\` trên \`private writeObject\` không phù hợp. Hai annotation phục vụ hai cách Java nhận diện method khác nhau.

**Sửa nhầm tên hoặc modifier rồi tin compiler sẽ bắt hết.** API \`@Serial\` khuyến khích compiler cảnh báo, không bảo đảm mọi compiler đều chặn từng trường hợp. Test behavior là thiết yếu.

**Cho rằng UID giữ nguyên thì mọi thay đổi đều tương thích.** Tương thích serialization còn phụ thuộc cấu trúc class, serial form, kiểu field, kế thừa, custom data và logic đọc/ghi.

**Viết \`writeObject\` có custom data nhưng \`readObject\` không đọc phần tương ứng.** Stream trở nên không nhất quán, có thể mất dữ liệu hoặc phát sinh lỗi khi deserialize.

**Gắn \`@Serial\` lên \`writeExternal\`/\`readExternal\`.** Đây là methods của \`Externalizable\`, dùng \`@Override\`, không phải nhóm target serialization declarations của \`@Serial\`.

**Dùng \`@Serial\` để tài liệu hóa serial form.** \`@serial\` trong JavaDoc comment mới thuộc cơ chế viết tài liệu. Hai tên chỉ khác chữ hoa/thường nhưng khác vai trò.

## 8. Tự kiểm tra kiến thức

1. Lớp \`Invoice implements Serializable\` có \`private static final long serialVersionUID = 2L;\`. Có nên gắn \`@Serial\`? **Có**, đây là field đặc biệt hợp lệ.
2. Lớp có \`@Serial private void readObject(ObjectInputStream in)\`, nhưng developer quên \`in.defaultReadObject()\`. Annotation có tự đọc những field mặc định không? **Không**. Phải thiết kế code đọc phù hợp với dữ liệu đã được ghi; không phải lúc nào cần \`defaultReadObject()\`, nhưng phải hiểu serial form.
3. Có thể lấy \`@Serial\` qua reflection runtime? **Không**, annotation có \`RetentionPolicy.SOURCE\`.
4. Có nên dùng \`@Serial\` trên \`writeExternal\`? **Không**. Đây là phương thức triển khai \`Externalizable\`.
5. Vì sao \`@Serial\` không bảo đảm một method \`writeObjects\` được gọi? **Vì cơ chế object serialization nhận diện đúng special method theo hợp đồng của nó; annotation chỉ đánh dấu ý định và hỗ trợ công cụ kiểm tra**.

## Tài liệu chuẩn để đối chiếu

- Java SE 21 API — \`java.io.Serial\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/Serial.html
- Java SE 21 API — \`java.io.Serializable\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/Serializable.html
- Java Object Serialization Specification (được liên kết từ các trang API trên).

Khi làm việc với \`@Serial\`, hãy đọc cả **khai báo special member** và **hợp đồng serialization của class**. Annotation giúp thể hiện mục đích và có thể hỗ trợ phát hiện sai sót từ sớm; kết quả lưu/khôi phục object vẫn do cơ chế serialization, serial form và logic thực tế quyết định.