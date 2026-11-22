# Yêu cầu constructor public không tham số của Externalizable trong Java

## 1. Tại sao Externalizable cần constructor public không tham số?

Trong **Java Object Serialization**, interface `java.io.Externalizable` cho phép một đối tượng tự quyết định **những byte nào được viết** và **thứ tự đọc lại các byte đó**. Nó mở rộng `Serializable` và khai báo hai phương thức:

- `public void writeExternal(ObjectOutput out) throws IOException` — ghi trạng thái đối tượng.
- `public void readExternal(ObjectInput in) throws IOException, ClassNotFoundException` — đọc dữ liệu và khôi phục trạng thái.

Đặc điểm khác thường: khi `ObjectInputStream.readObject()` giải tuần tự hóa đối tượng `Externalizable`, nó **tạo một instance bằng cách gọi constructor public không tham số của lớp đó**, sau đó mới gọi `readExternal()`.

~~~text
GHI (serialization)
  new Person("An", 20)
         |
  ObjectOutputStream.writeObject(person)
         |
     writeExternal(out)
         |
   object stream chứa class metadata + dữ liệu do ta ghi

ĐỌC (deserialization)
  ObjectInputStream.readObject()
         |
  tìm public Person()  <--- BẮT BUỘC có
         |
  chạy Person() + chuỗi constructor superclass
         |
     readExternal(in)
         |
  Person được trả về cho ứng dụng
~~~

**Điều kiện bắt buộc:** lớp được giải tuần tự hóa theo cơ chế `Externalizable` phải có **constructor không tham số (`()`), có mức truy cập `public`**. Chỉ có constructor `private`, `protected` hoặc package-private (không ghi modifier) là **không đủ**. Chỉ có constructor nhận tham số cũng không đủ.

Thiếu điều kiện này có thể **vẫn biên dịch và ghi object thành công**, nhưng khi đọc lại sẽ thất bại, thường bằng `java.io.InvalidClassException` với thông điệp như `no valid constructor`. Đừng lầm tưởng đây là quy tắc chung của mọi `Serializable`; đây là điểm riêng rất quan trọng của `Externalizable`.

## 2. Trước hết hiểu Externalizable và Serializable

Hai lựa chọn đều tham gia cơ chế object serialization của Java, nhưng khác nhau về quyền kiểm soát trạng thái và cách khởi tạo lại object.

| Khía cạnh | `Serializable` thông thường | `Externalizable` |
| --- | --- | --- |
| Interface | Marker interface `Serializable`. | `Externalizable extends Serializable`, có hai phương thức công khai. |
| Ghi mặc định | JVM tự xử lý các field đủ điều kiện; có thể tùy biến bằng `private writeObject`. | Chương trình phải tự viết nội dung trong `writeExternal`. |
| Đọc mặc định | JVM phục hồi state theo serialization protocol; có thể tùy biến bằng `private readObject`. | Chương trình phải tự phục hồi state trong `readExternal`. |
| Constructor của chính lớp serializable | **Không** chạy theo cách tạo object thông thường khi deserialize instance `Serializable` thường. | **Có chạy** public no-arg constructor của lớp `Externalizable`. |
| Superclass không serializable | Constructor không tham số truy cập được của superclass đầu tiên không serializable được chạy. | Constructor chain thông thường được gọi từ constructor public no-arg. |
| Field initialization | Field initializer/constructor của chính lớp Serializable không chạy như `new` khi đọc object thông thường. | Field initializer và constructor body của Externalizable chạy theo vòng đời constructor thông thường. |
| `transient` | Mặc định không serialize field transient. | Không tự giới hạn `writeExternal`: lập trình viên quyết định dữ liệu nào được ghi, kể cả field transient nếu cố ý. |
| Độ khó | Thường đơn giản hơn, nhưng vẫn phải quản lý version/độ tin cậy. | Nhiều quyền kiểm soát hơn, đi kèm trách nhiệm định dạng, tương thích và constructor. |

Ví dụ:

~~~java
class SimpleUser implements java.io.Serializable {
    private String name;
    private int age;
    // Không bắt buộc khai báo public SimpleUser().
}
~~~

Đoạn minh họa này không có `main`, chỉ cho thấy `Serializable` không áp dụng quy tắc **public no-arg constructor của chính lớp** như `Externalizable`. Đừng suy ra rằng lớp Serializable không cần bất kỳ constructor phù hợp nào trong hệ kế thừa: **superclass đầu tiên không Serializable** vẫn phải có constructor không tham số với quyền truy cập thích hợp.

### 2.1. Tại sao Java không dùng constructor có tham số?

Khi đọc object từ stream, `ObjectInputStream` có dữ liệu byte nhưng không có quy tắc tổng quát để chọn overload constructor như `Person(String, int)`, `Person(String)` hay `Person(int)`. `Externalizable` quy định một quy trình nhất quán:

1. Tạo object bằng constructor **public không tham số**.
2. Giao đối tượng `ObjectInput` cho `readExternal`.
3. Chính `readExternal` biết **đọc giá trị nào** và **gán vào field nào**.

Vì thế constructor no-arg phải tạo được một **trạng thái ban đầu hợp lệ để tiếp tục phục hồi**, còn `readExternal` chịu trách nhiệm chuyển instance đó thành trạng thái đã lưu.

## 3. Cú pháp đúng của constructor

Một lớp `Externalizable` cơ bản:

~~~java
import java.io.Externalizable;
import java.io.IOException;
import java.io.ObjectInput;
import java.io.ObjectOutput;

public class ExternalUser implements Externalizable {

    private String username;
    private int level;

    // BẮT BUỘC: constructor public và không nhận tham số.
    public ExternalUser() {
    }

    // Constructor nhận tham số là TÙY CHỌN, chỉ tiện tạo object mới.
    public ExternalUser(String username, int level) {
        this.username = username;
        this.level = level;
    }

    @Override
    public void writeExternal(ObjectOutput out) throws IOException {
        out.writeUTF(username);
        out.writeInt(level);
    }

    @Override
    public void readExternal(ObjectInput in)
            throws IOException, ClassNotFoundException {
        username = in.readUTF();
        level = in.readInt();
    }
}
~~~

Đây là **một lớp Java có thể biên dịch** khi lưu thành `ExternalUser.java`, nhưng không có `main` độc lập. Cần bổ sung xử lý trường `username == null` trong code production; `writeUTF` không chấp nhận `null`. Với dữ liệu không tin cậy, `readExternal` cũng phải giới hạn/kiểm tra giá trị của các field.

**Hai constructor cùng tồn tại được:** Java chọn overload có tham số khi ứng dụng chủ động gọi `new ExternalUser("an", 3)`; khi `ObjectInputStream` phục hồi object Externalizable, nó dùng `public ExternalUser()`.

Một constructor đúng phải thỏa cả hai điều kiện:

~~~text
public + không có tham số

public ExternalUser() {}        // ĐÚNG
protected ExternalUser() {}     // SAI đối với Externalizable deserialization
ExternalUser() {}              // SAI (package-private)
private ExternalUser() {}      // SAI
public ExternalUser(int id) {} // SAI nếu không có public ExternalUser()
~~~

**Đừng nhầm default constructor với constructor không tham số do tự viết:** nếu lớp không khai báo bất kỳ constructor nào, trình biên dịch Java tự sinh một constructor no-arg có cùng mức truy cập với lớp. Nhưng **ngay khi bạn khai báo bất kỳ constructor nào**, constructor mặc định đó không còn được tự tạo. Trong class `public ExternalUser` có `ExternalUser(String)`, bạn **phải viết thêm** `public ExternalUser()`.

## 4. Vòng đời chính xác lúc deserialize

Khi có `ObjectOutputStream` và `ObjectInputStream`:

~~~text
1) Application tạo object bằng constructor tùy chọn.
2) out.writeObject(object)
   - Kiểm tra class/serialization protocol.
   - Gọi object.writeExternal(out) để ghi custom data.
3) in.readObject()
   - Đọc descriptor và xác định class cần tái tạo.
   - Kiểm tra/chuẩn bị việc tạo instance Externalizable.
   - Gọi constructor public no-arg của Externalizable class.
   - Constructor gọi super() theo chuỗi constructor Java.
   - Gọi object.readExternal(in) để nạp custom state.
   - Hoàn tất serialization protocol rồi trả về tham chiếu object.
~~~

Vì constructor **thực sự chạy**, bạn cần để ý cả:

- **Field initializer** (ví dụ `private List<String> tags = new ArrayList<>();`) được chạy theo quy trình tạo object thông thường trước body constructor của lớp.
- **Side effects** trong constructor như log, tăng bộ đếm, gọi service hoặc đăng ký observer cũng có thể xảy ra khi deserialize.
- **Validation/invariant**: constructor có thể tạo state mặc định; `readExternal` thay thế các field bằng giá trị từ stream. Phải xác thực giá trị sau khi đọc để instance không rơi vào trạng thái bất hợp lệ.
- **Chuỗi super constructor**: `public Child() { super(); }` phải biên dịch được; nếu superclass không có constructor không tham số truy cập được, cần điều chỉnh thiết kế lớp.

Không nên thực hiện side effects nguy hiểm hoặc không thể hoàn tác trong public no-arg constructor vì bất kỳ lượt đọc object Externalizable hợp lệ nào cũng có thể kích hoạt chúng. Đó là một lý do phải coi Java deserialization là bề mặt tấn công khi nguồn byte không tin cậy.

## 5. Ví dụ Java 17+ đầy đủ: chứng minh thứ tự constructor và readExternal

Lưu toàn bộ chương trình sau trong tệp `ExternalizableConstructorDemo.java`.

~~~java
import java.io.*;

public class ExternalizableConstructorDemo {

    public static class Entry implements Externalizable {
        @Serial
        private static final long serialVersionUID = 1L;

        private String name;
        private int count;

        // ObjectInputStream gọi constructor này khi DESERIALIZE.
        public Entry() {
            System.out.println("constructor: public no-arg");
        }

        // Ứng dụng dùng constructor này để tạo object ban đầu.
        public Entry(String name, int count) {
            this.name = name;
            this.count = count;
        }

        @Override
        public void writeExternal(ObjectOutput out) throws IOException {
            System.out.println("writeExternal");
            out.writeUTF(name);
            out.writeInt(count);
        }

        @Override
        public void readExternal(ObjectInput in)
                throws IOException, ClassNotFoundException {
            System.out.println("readExternal");
            this.name = in.readUTF();
            this.count = in.readInt();
        }

        @Override
        public String toString() {
            return "Entry{name='" + name + "', count=" + count + "}";
        }
    }

    public static void main(String[] args) throws Exception {
        Entry original = new Entry("Hoa", 7);
        byte[] bytes;

        try (ByteArrayOutputStream raw = new ByteArrayOutputStream();
             ObjectOutputStream out = new ObjectOutputStream(raw)) {

            out.writeObject(original);
            out.flush();
            bytes = raw.toByteArray();
        }

        System.out.println("afterSerialize=" + original);

        try (ObjectInputStream in = new ObjectInputStream(
                new ByteArrayInputStream(bytes))) {

            Entry restored = (Entry) in.readObject();
            System.out.println("afterRead=" + restored);
        }
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac ExternalizableConstructorDemo.java
java ExternalizableConstructorDemo
~~~

**Stdout chính xác:** 

~~~text
writeExternal
afterSerialize=Entry{name='Hoa', count=7}
constructor: public no-arg
readExternal
afterRead=Entry{name='Hoa', count=7}
~~~

### 5.1. Vì sao thứ tự in ra như vậy?

1. `new Entry("Hoa", 7)` dùng constructor **có tham số**, nên không in dòng `constructor: public no-arg`.
2. `out.writeObject(original)` gọi `writeExternal()`, in `writeExternal` rồi ghi username và count.
3. Sau khi serialize, `original` vẫn là object cũ; dòng `afterSerialize=...` không có thao tác tạo object mới.
4. `in.readObject()` cần một instance Externalizable mới nên gọi `public Entry()`, in `constructor: public no-arg`.
5. Sau constructor, Java gọi `readExternal()` để đọc lại String và int đúng thứ tự đã ghi; dòng `readExternal` được in.
6. `toString()` của instance đã phục hồi cho thấy `name` và `count` đúng như bản ban đầu.

**Kiểm nghiệm:** ví dụ này đã được biên dịch với tùy chọn `javac --release 17` và chạy thành công trên runtime tương thích Java 17+; stdout nêu trên lấy từ quá trình chạy thực tế. Tính xác định không phụ thuộc timestamp, địa chỉ đối tượng hay đường dẫn tệp.

### 5.2. Tại sao dùng `public static class Entry`?

`Entry` là một **static nested class**: không có tham chiếu ngầm đến một instance lớp bao ngoài. Constructor `public Entry()` thực sự là constructor không tham số trên lớp bytecode tương ứng, cho nên phù hợp với Externalizable.

Ngược lại, một **non-static inner class** thường mang tham số constructor ngầm biểu diễn enclosing instance. Dù người viết khai báo `public Inner()` ở mã nguồn, chữ ký constructor ở mức bytecode vẫn cần tham chiếu đối tượng ngoài. Theo Java Serialization Specification, cơ chế `Externalizable` **không phù hợp** với inner class gắn enclosing instance; nên dùng top-level class hoặc static nested class nếu cần Externalizable.

## 6. Trường hợp sai: thiếu public no-arg constructor

Đây là một lớp ví dụ **có thể biên dịch**, nhưng không thể deserialize bình thường bằng cơ chế Externalizable:

~~~java
public static class BadEntry implements Externalizable {
    private String value;

    public BadEntry(String value) {
        this.value = value;
    }

    @Override
    public void writeExternal(ObjectOutput out) throws IOException {
        out.writeUTF(value);
    }

    @Override
    public void readExternal(ObjectInput in)
            throws IOException, ClassNotFoundException {
        value = in.readUTF();
    }
}
~~~

**Lưu ý:** đoạn trên dành để đặt bên trong một lớp Java có import `java.io.Externalizable`, `ObjectInput`, `ObjectOutput` và `IOException`; nó không phải top-level class độc lập do có `static`.

Vì `BadEntry` đã có `public BadEntry(String value)`, Java **không sinh** constructor mặc định no-arg. Quy trình thường là:

~~~text
BadEntry original = new BadEntry("x")   -> hợp lệ
ObjectOutputStream.writeObject(original)
                                        -> gọi writeExternal, có thể thành công
ObjectInputStream.readObject()           -> cần public BadEntry()
                                        -> không có
                                        -> InvalidClassException
~~~

Không có gì trong `writeExternal`/`readExternal` sửa được thiếu sót này. Cách khắc phục:

~~~java
public BadEntry() {
    // Cho phép ObjectInputStream khởi tạo lại instance.
}
~~~

Đảm bảo constructor thật sự được khai báo **trong đúng lớp Externalizable cần deserialize**, không phải chỉ ở lớp cha hoặc một lớp khác.

### 6.1. Constructor private/protected/package-private cũng không đạt yêu cầu

~~~java
public class OtherBadEntry implements Externalizable {
    private OtherBadEntry() {} // KHÔNG phải public
    // Cần bổ sung hai phương thức public writeExternal/readExternal.
}
~~~

Đây là **mảnh minh họa không đầy đủ**, không dùng để compile độc lập. Dù code ở cùng package gọi được một constructor package-private, Object Serialization của Externalizable yêu cầu **public no-arg constructor**. Sự khác nhau về accessibility không phải chi tiết trang trí.

### 6.2. Không cần làm mọi field public

Yêu cầu public áp dụng với **constructor không tham số** và hai method thuộc contract `Externalizable`. Các field vẫn có thể và nên là `private`, miễn `readExternal` trong class có cách phục hồi chúng. Đừng thay tất cả field thành public chỉ để serializer dùng được: đó là việc không liên quan và làm hỏng encapsulation.

## 7. Constructor phải làm gì và không nên làm gì?

### 7.1. Constructor nên tạo state tối thiểu an toàn

~~~java
public ExternalOrder() {
    this.items = new ArrayList<>();
    this.status = "NEW";
}
~~~

Đây là đoạn minh họa thuộc một class có `items` và `status` phù hợp. Khi deserialize, các giá trị này chỉ đóng vai trò **trạng thái mặc định ban đầu**; `readExternal` phải đọc dữ liệu theo định dạng đã ghi và cập nhật fields cần thiết.

Việc constructor này chạy lúc read có thể tiện để thiết lập collections hoặc invariant ban đầu. Tuy nhiên, **không** có nghĩa bạn được bỏ `readExternal` hay mặc định các field từ object gốc sẽ tự chui vào constructor. Externalizable chỉ phục hồi những gì chương trình viết/đọc theo protocol.

### 7.2. Tránh side effects trong constructor

Không nên tự động:

- Gửi email, ghi database, đặt đơn hàng hoặc gọi thanh toán.
- Khởi động thread, mở socket, đăng ký job lâu dài.
- Dùng dữ liệu nhận chưa được xác thực để truy cập tệp hay hệ thống khác.
- Dựa vào constructor có tham số để dựng invariant mà quên rằng deserialize dùng constructor **không tham số**.
- Coi việc constructor được gọi là sự kiện “object đã hoàn toàn được phục hồi”: `readExternal` còn phải chạy sau đó.

Nếu việc khởi tạo tốn nhiều chi phí và khó an toàn khi deserialize, cân nhắc dùng một mô hình DTO hoặc định dạng dữ liệu khác thay vì Externalizable.

## 8. Thứ tự writeExternal và readExternal phải khớp nhau

`Externalizable` trao toàn quyền nội dung stream cho người viết class. Nếu ghi:

~~~java
@Override
public void writeExternal(ObjectOutput out) throws IOException {
    out.writeInt(id);
    out.writeUTF(name);
    out.writeBoolean(active);
}
~~~

thì phải đọc lại cùng thứ tự và đúng kiểu:

~~~java
@Override
public void readExternal(ObjectInput in)
        throws IOException, ClassNotFoundException {
    id = in.readInt();
    name = in.readUTF();
    active = in.readBoolean();
}
~~~

Hai đoạn này là **mảnh method minh họa** bên trong một class có các field `id`, `name`, `active` và import phù hợp.

**Sai phổ biến:** gọi `readUTF()` trước `readInt()` khi writer ghi int trước. Tùy dữ liệu cụ thể, kết quả có thể là exception vì đọc sai định dạng, giá trị sai hoặc stream bị lệch vị trí.

Không có default field serialization tự cứu khi nội dung tự viết bị thiếu: nếu một field quan trọng như `balance` không được `writeExternal` ghi và `readExternal` đọc, nó sẽ giữ giá trị được thiết lập trong constructor/field initializer (hoặc mặc định kiểu Java), không tự khôi phục từ object gốc.

### 8.1. Đừng gọi defaultWriteObject/defaultReadObject trong Externalizable

`ObjectOutputStream.defaultWriteObject()` và `ObjectInputStream.defaultReadObject()` là phần của cơ chế custom serialization **`Serializable`** thông qua các private method `writeObject/readObject` thích hợp. `Externalizable` không dùng các phương thức đó như cách thay thế `writeExternal/readExternal`.

Khi triển khai Externalizable, hãy chủ động dùng `ObjectOutput.writeInt/writeUTF/writeObject` và đối xứng `ObjectInput.readInt/readUTF/readObject` theo định dạng do bạn xác định. Trường hợp superclass cũng quản lý trạng thái externalized phải có hợp đồng gọi `super.writeExternal(...)`/`super.readExternal(...)` thích hợp nếu việc kế thừa đó tồn tại.

### 8.2. Nếu field chứa object

~~~java
@Override
public void writeExternal(ObjectOutput out) throws IOException {
    out.writeObject(address);
}

@Override
public void readExternal(ObjectInput in)
        throws IOException, ClassNotFoundException {
    address = (Address) in.readObject();
}
~~~

Đây là **đoạn minh họa**; `Address` cần là một type serializable theo hợp đồng phù hợp hoặc được thay bằng dạng dữ liệu khác. Khi gọi `writeObject/readObject` lồng bên trong Externalizable, cơ chế Java object serialization vẫn xử lý metadata, object identity và đồ thị tham chiếu theo protocol; các object lồng nhau cũng phải an toàn để deserialize.

Đừng tự cast dữ liệu ngoài luồng mà không kiểm tra loại, giới hạn object graph và tính hợp lệ của nội dung.

## 9. serialVersionUID có thay thế constructor không?

**Không.** Hai thứ giải quyết hai vấn đề khác nhau:

| Thành phần | Mục đích |
| --- | --- |
| `public ClassName()` | Cung cấp cách khởi tạo instance Externalizable lúc deserialize. |
| `writeExternal/readExternal` | Xác định payload thực sự lưu và cách phục hồi. |
| `serialVersionUID` | Tham gia kiểm tra tính tương thích class descriptor khi serialize/deserialize theo quy tắc Java Serialization. |
| Version byte riêng trong external payload | Giúp chương trình phân biệt và nâng cấp định dạng custom theo thời gian. |

Ví dụ:

~~~java
@Serial
private static final long serialVersionUID = 1L;
~~~

`@Serial` có trong Java 17; annotation này giúp trình biên dịch/công cụ nhận ra thành viên dùng trong cơ chế serialization. Đặt `serialVersionUID` ổn định **không khiến một lớp thiếu public no-arg constructor trở nên hợp lệ**. Nó cũng không tự chỉnh các trường dữ liệu khi `writeExternal` đổi thứ tự hoặc định dạng.

### 9.1. Version dữ liệu tự định nghĩa

Nếu một class từng ghi `id` rồi `name`, về sau muốn thêm `active`, cần có kế hoạch tương thích. Một lựa chọn là ghi version trong custom payload:

~~~java
@Override
public void writeExternal(ObjectOutput out) throws IOException {
    out.writeInt(2); // Payload format version.
    out.writeInt(id);
    out.writeUTF(name);
    out.writeBoolean(active);
}

@Override
public void readExternal(ObjectInput in)
        throws IOException, ClassNotFoundException {

    int version = in.readInt();
    if (version == 1) {
        id = in.readInt();
        name = in.readUTF();
        active = false;
    } else if (version == 2) {
        id = in.readInt();
        name = in.readUTF();
        active = in.readBoolean();
    } else {
        throw new IOException("Unsupported version: " + version);
    }
}
~~~

Đây là **hai method minh họa**, các field thuộc class bao ngoài và protocol version 1 giả định cũng đã ghi version=1 ở đầu. Nếu version 1 trong thực tế **không** ghi trường version, không thể chỉ thêm `readInt()` này rồi tự suy ra version của stream cũ; phải có kế hoạch migration/định dạng bao bọc khác.

Version payload là lựa chọn của ứng dụng, không phải điều Java tự cung cấp cho Externalizable. Tùy mục tiêu tương thích, đôi khi nên dùng format như JSON/CBOR/Protocol Buffers thay vì Java native object serialization.

## 10. Thừa kế và yêu cầu constructor

### 10.1. Constructor của superclass

Khi class Externalizable được tạo qua constructor no-arg, Java vẫn thực hiện **normal constructor chaining**:

~~~java
class Base {
    Base() {
        System.out.println("base constructor");
    }
}

public class Child extends Base implements Externalizable {
    public Child() {
        super();
        System.out.println("child constructor");
    }

    // Cần triển khai writeExternal/readExternal.
}
~~~

Đây là **mảnh minh họa** về thứ tự constructor, chưa có method bắt buộc nên không compile độc lập. Nếu được triển khai đầy đủ, khi `Child` được deserialize, constructor `Base()` chạy trước body `Child()`.

Nếu `Base` chỉ có `Base(String required)` và không có no-arg, `Child()` không thể gọi `super()` mặc định. Muốn có constructor no-arg ở Child, bạn phải viết lời gọi constructor superclass hợp lệ, chẳng hạn `super("default")` (nếu được phép) hoặc thay đổi thiết kế superclass. Điều này là quy tắc **constructor Java thông thường**, không phải một ngoại lệ do Externalizable tạo ra.

### 10.2. Subclass có kế thừa Externalizable?

Một subclass của lớp implement `Externalizable` cũng thuộc họ Externalizable. Nếu nó được serialize/deserialize với class cụ thể đó, cơ chế phải có cách khởi tạo class đúng contract. Đừng cho rằng public no-arg constructor của **lớp cha** tự động trở thành public no-arg constructor của **lớp con** — constructor **không được kế thừa** trong Java.

Nếu subclass khai báo constructor có tham số mà không khai báo public no-arg tương ứng, nó có thể gặp cùng vấn đề lúc deserialize. Khi subclass override `writeExternal/readExternal`, nó cũng phải quản lý trạng thái superclass theo quy ước đã thiết kế.

### 10.3. Non-static inner class

~~~java
public class Outer {
    public class Inner implements Externalizable {
        public Inner() { }

        @Override
        public void writeExternal(ObjectOutput out) throws IOException { }

        @Override
        public void readExternal(ObjectInput in)
                throws IOException, ClassNotFoundException { }
    }
}
~~~

Đây là **mảnh code minh họa**, cần import java.io và có thể compile trong bối cảnh class phù hợp, nhưng **không nên dùng làm Externalizable object**. `Inner` giữ liên kết ngầm tới `Outer`, nên constructor thực tế cần enclosing instance. Java Serialization Specification nêu rõ Externalizable không áp dụng đúng cho inner class dạng này. Hãy chuyển thành **static nested class** hoặc top-level class.

## 11. Lỗi phổ biến và cách chẩn đoán

| Triệu chứng | Nguyên nhân | Hướng sửa |
| --- | --- | --- |
| `InvalidClassException: no valid constructor` khi `readObject()` | Externalizable class thiếu public no-arg constructor hợp lệ. | Thêm `public ClassName() {}` và bảo đảm superclass constructor chain hợp lệ. |
| Code biên dịch, `writeObject` thành công nhưng `readObject` thất bại | Serializer không cần public no-arg để ghi, nhưng cần lúc đọc. | Kiểm thử cả round-trip, không chỉ ghi file. |
| Constructor no-arg không được trình biên dịch tự tạo | Đã khai báo constructor có tham số. | Tự viết overload no-arg public. |
| `readExternal` đọc sai giá trị hoặc EOF | Thứ tự/số lượng/kiểu read khác với write. | Định nghĩa rõ binary format, versioning và test round-trip. |
| Sau deserialize một field vẫn null/0 | Field chưa được write/read, hoặc constructor chỉ đặt default. | Kiểm tra các field cần lưu và logic khôi phục. |
| Một action được thực hiện “lần nữa” khi đọc object | Constructor có side effect. | Giữ constructor đơn giản và không gây tác động bên ngoài. |
| `InvalidClassException` dù constructor có tồn tại | Có thể sai access, class version, class descriptor/filter hoặc điều kiện serialization khác. | Kiểm tra exact exception/cause, class loader, `serialVersionUID`, public ctor và filter. |
| Inner Externalizable không deserialize được | Constructor bytecode của non-static inner cần outer instance. | Dùng top-level hoặc static nested class. |
| Object restored vi phạm invariant | `readExternal` đưa dữ liệu chưa validate vào field. | Kiểm tra bounds/types/required fields, throw `InvalidObjectException` nếu state không hợp lệ. |
| Stream không tương thích giữa bản phát hành | `writeExternal` đổi format nhưng `readExternal` không hỗ trợ bản cũ. | Có payload format version và migration test phù hợp. |

### 11.1. Kiểm tra public no-arg bằng Reflection

Có thể xác minh constructor mà không tự deserialize:

~~~java
import java.lang.reflect.Constructor;

Constructor<?> ctor = Entry.class.getConstructor();
System.out.println(ctor.getParameterCount() == 0);
~~~

Đây là **mảnh minh họa**, `Entry` cần là class đang kiểm tra và method bao ngoài phải xử lý `NoSuchMethodException`. `getConstructor()` chỉ trả về **public constructor** khớp signature. Nếu có constructor no-arg nhưng private/package-private, lệnh này vẫn không tìm thấy.

Reflection chỉ kiểm tra một phần yêu cầu; nó **không chứng minh** class có format externalization đúng, super constructor không ném lỗi, hoặc dữ liệu trong stream tương thích. Cách thử cuối cùng vẫn là một **round-trip serialize → deserialize** với case điển hình và case lỗi.

## 12. Bảo mật: public constructor khiến deserialize có thể chạy code

Java native deserialization của dữ liệu không tin cậy là nguy hiểm vì đọc bytes có thể:

- Tải class, tạo đối tượng và chạy constructor của Externalizable.
- Gọi `readExternal` do ứng dụng viết, trong đó có thể có side effects hoặc xử lý dữ liệu chưa kiểm tra.
- Đọc tiếp object lồng nhau qua `ObjectInput.readObject`, mở rộng object graph ngoài dự kiến.
- Làm cạn tài nguyên nếu stream khai báo/đòi dữ liệu quá lớn hoặc chứa cấu trúc sâu.
- Chạm vào các class nguy hiểm/gadget có sẵn trên classpath trong một số môi trường.

**Không coi public no-arg constructor là chứng thực nguồn dữ liệu.** Đây chỉ là điều kiện tạo instance. Cần đánh giá dữ liệu input có được xác thực và tin cậy hay chưa.

### 12.1. Giới hạn giá trị trong readExternal

~~~java
@Override
public void readExternal(ObjectInput in)
        throws IOException, ClassNotFoundException {

    int inputCount = in.readInt();

    if (inputCount < 0 || inputCount > 10_000) {
        throw new InvalidObjectException("count out of range");
    }

    this.count = inputCount;
}
~~~

Đây là **method minh họa** thuộc class có field `count` và import `java.io.InvalidObjectException`. Nó minh họa kiểm tra đầu vào trước khi gán state. Trong class có nhiều field, đừng công bố/đăng ký object cho code bên ngoài khi trạng thái mới được phục hồi một phần.

### 12.2. Serialization filter

Java 17 cung cấp `ObjectInputFilter` để giới hạn class và kích thước đồ thị đối tượng khi deserialize.

~~~java
ObjectInputFilter filter =
        ObjectInputFilter.Config.createFilter(
                "maxdepth=10;maxrefs=100;maxbytes=100000;com.example.dto.*;!*");

input.setObjectInputFilter(filter);
Object value = input.readObject();
~~~

Đây là **mảnh minh họa**: `input` là một `ObjectInputStream` do ứng dụng tạo, và phải set filter trước khi đọc. Hãy điều chỉnh allowlist cho đúng tập class dự kiến, bao gồm những class lồng cần thiết; pattern trên chỉ là ví dụ cấu hình, không phải mặc định dùng được cho mọi dự án. Filter là **defense in depth**, không đủ để biến dữ liệu không tin cậy thành an toàn tuyệt đối.

Nếu không có yêu cầu bắt buộc phải dùng Java native serialization, một protocol với schema và parse/validation rõ ràng thường dễ giới hạn rủi ro hơn.

## 13. Checklist thực hành Externalizable

Trước khi viết:

1. **Class thực sự implement `Externalizable`?** Nếu chỉ `Serializable`, quy tắc constructor khác.
2. **Có `public ClassName()` đúng signature?** Không tham số; quyền public; thuộc đúng class được phục hồi.
3. **Constructor chain của superclass chạy hợp lệ?** Constructor Java thông thường không được kế thừa.
4. **Dùng static nested/top-level class?** Tránh non-static inner class gắn enclosing object.
5. **`writeExternal` và `readExternal` có public và đúng signature?** Dùng `@Override` để compiler bắt lỗi.
6. **Thứ tự/kiểu byte viết và đọc đối xứng?** Ghi `int` thì đọc `int`, ghi `UTF` thì đọc `UTF`.
7. **Tất cả state cần thiết được lưu và phục hồi?** Field mặc định của constructor không thay thế dữ liệu ban đầu.
8. **Đã xác định cách xử lý null và optional fields?** `writeUTF(null)` không hợp lệ; cần presence marker/schema.
9. **Có `serialVersionUID` ổn định và version custom payload khi cần?** Hai thứ không thay thế nhau.
10. **Constructor và `readExternal` không có side effect nguy hiểm?** Deserialization có thể gọi cả hai.
11. **Có validate dữ liệu không tin cậy và giới hạn kích thước?** Tránh malformed stream và cạn tài nguyên.
12. **Có test round-trip và test phiên bản cũ?** Compile/serialize thành công chưa chứng minh deserialize thành công.

## 14. Câu hỏi tự kiểm tra

1. **Lớp implement Externalizable có bắt buộc public no-arg constructor không?** Có, để `ObjectInputStream` có thể khởi tạo khi deserialize.
2. **Chỉ có `public User(String name)` có đủ không?** Không, Java không tự sinh `User()` khi đã có constructor do bạn viết.
3. **`private User()` có đạt điều kiện không?** Không. Quyền truy cập phải là `public`.
4. **Constructor public no-arg chạy trước hay sau readExternal?** Trước, rồi `readExternal` khôi phục state.
5. **Constructor có tham số dùng khi ứng dụng tạo object ban đầu có được gọi lại khi deserialize không?** Không theo quy trình Externalizable mặc định; hệ thống dùng public no-arg.
6. **Có cần public tất cả field không?** Không. Field vẫn có thể private; `readExternal` chịu trách nhiệm gán.
7. **Tại sao ghi file thành công vẫn có thể đọc file thất bại?** Yêu cầu constructor phục vụ deserialize, cộng các điều kiện tương thích và định dạng stream.
8. **Serializable thường có chạy constructor của chính lớp Serializable khi deserialize không?** Không theo cơ chế thông thường; constructor của superclass đầu tiên không Serializable có thể được chạy.
9. **Vì sao non-static inner class không phù hợp Externalizable?** Có tham chiếu outer instance ngầm trong constructor bytecode, không cung cấp public no-arg constructor thực sự theo yêu cầu.
10. **`serialVersionUID` thay được constructor không?** Không, nó phục vụ kiểm tra class version chứ không tạo instance.
11. **Một field không được writeExternal ghi, readExternal cũng không đọc thì thế nào?** Nó giữ giá trị mặc định/constructor đã tạo, không tự phục hồi từ object gốc.
12. **Trật tự writeUTF rồi writeInt có thể đọc bằng readInt rồi readUTF không?** Không; định dạng sẽ lệch.
13. **Có nên dùng constructor để gửi email ngay sau khi object được tạo không?** Không, vì deserialize cũng gọi constructor và có thể kích hoạt side effect ngoài ý muốn.
14. **Làm sao phát hiện thiếu public no-arg trước khi đưa lên production?** Dùng reflection `getConstructor()` và quan trọng hơn là test serialize/deserialize round-trip.
15. **readExternal đọc data lạ có thể làm gì?** Validate schema, độ dài, giá trị; ném `IOException`/`InvalidObjectException` nếu dữ liệu sai.
16. **Có nên deserialize trực tiếp bytes từ người không tin cậy không?** Nên tránh khi có thể; nếu buộc dùng cần authentication, filtering, validation và giới hạn tài nguyên.

## 15. Tài liệu chính thức

- [Externalizable — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Externalizable.html): yêu cầu public no-arg constructor, `readExternal` và `writeExternal`.
- [ObjectInputStream — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputStream.html): khôi phục object, luồng constructor và cảnh báo dữ liệu không tin cậy.
- [Java Object Serialization Specification: Object Input](https://docs.oracle.com/en/java/javase/17/docs/specs/serialization/input.html): thứ tự cấp phát object, gọi constructor và đọc trạng thái.
- [Java Object Serialization Specification: System Architecture](https://docs.oracle.com/en/java/javase/17/docs/specs/serialization/serial-arch.html): hợp đồng Externalizable và giới hạn inner class.
- [ObjectInputFilter — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputFilter.html): giới hạn class/object graph trong quá trình deserialize.

**Ghi nhớ:** `Externalizable` trao quyền ghi/đọc trạng thái cho `writeExternal` và `readExternal`. Để tạo lại object, `ObjectInputStream` **cần gọi `public ClassName()` trước `readExternal()`**. Chỉ constructor có tham số, private, protected hoặc package-private đều **không đủ**. Hãy thiết kế constructor an toàn, thực hiện định dạng ghi/đọc đối xứng, validate state và kiểm thử vòng ghi-đọc bằng Java 17.
