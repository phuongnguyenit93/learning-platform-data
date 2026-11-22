# Ghi lại đối tượng đã thay đổi, reset và cache handle

## 1. Vấn đề: sửa đối tượng nhưng dữ liệu nhận vẫn cũ

Khi dùng Java Object Serialization, gọi `ObjectOutputStream.writeObject(x)` lần đầu thường ghi trạng thái đối tượng và cấp **handle** (định danh tham chiếu trong luồng). Nếu về sau thay đổi field của **cùng instance** rồi gọi `writeObject(x)` lần nữa, stream thường chỉ ghi một **back-reference** tới handle cũ. `ObjectInputStream.readObject()` ở phía nhận có thể trả lại chính instance đã đọc lần đầu với trạng thái cũ.

Đây là tính năng bảo toàn cấu trúc **object graph**, không phải lỗi buffering. Nếu hai field cùng tham chiếu một object, reader cần tái tạo quan hệ `a.ref == b.ref`. Nếu graph có chu trình A → B → A, bảng handles giúp tránh duyệt vô hạn.

Sự khác biệt quan trọng:

- `writeObject(x)`: đối tượng chưa được ghi thì ghi định nghĩa; nếu **đã có handle** thì có thể ghi reference.
- `reset()`: tạo một ranh giới mới trong serialization stream, bỏ state về những đối tượng đã ghi; lần ghi sau sẽ tuần tự hóa graph như mới.
- `writeUnshared(x)`: buộc ghi mới **root object** của lời gọi, nhưng không nhất thiết làm mới các object con đã có handles.
- `flush()`: đẩy bytes đã encode sang output bên dưới; **không** xóa handles.

Không dùng `serialVersionUID` để theo dõi object mutation: UID phục vụ compatibility của class, không phải số phiên bản nội dung từng object.

## 2. Cơ chế bảng handles

```text
Writer, cùng một ObjectOutputStream:
    writeObject(x)  -> Object definition + handle H
    writeObject(x)  -> Reference to H

Reader, cùng một ObjectInputStream:
    readObject()    -> Tạo object y, lưu H -> y
    readObject()    -> Trả lại chính y
```

Bảng handle là **theo stream instance**, không phải global cache JVM; object identity (`==`) khác so sánh nội dung `equals()`. Hai đối tượng khác nhau có cùng field vẫn có thể được ghi độc lập.

Ví dụ `Account` được ghi một lần với `balance=10`; sau đó trong JVM gửi nó được sửa thành `balance=20`. Nếu lần thứ hai chỉ là reference đến handle, bản đọc thứ hai không tự thành 20. **ObjectOutputStream không giám sát field changes và không tự tạo delta.**

Đối tượng được encode là **toàn graph các field đủ điều kiện**, trừ trường hợp `transient`, `static` hoặc custom serialization. Một field chứa đối tượng không hỗ trợ `Serializable` có thể khiến `NotSerializableException`. Bảng handles còn ghi nhớ những object con và class descriptors đã gặp; điều đó quan trọng khi reset, writeUnshared và vận hành stream dài hạn.

## 3. Ví dụ Java 17: ghi cũ, reset, rồi ghi mới

Tạo file `SerializationHandleDemo.java`:

```java
import java.io.*;

public class SerializationHandleDemo {
  static class Message implements Serializable {
    private static final long serialVersionUID = 1L;
    String text;
    Message(String text) { this.text = text; }
  }
  public static void main(String[] args) throws Exception {
    Message message = new Message("before");
    ByteArrayOutputStream bytes = new ByteArrayOutputStream();
    try (ObjectOutputStream out = new ObjectOutputStream(bytes)) {
      out.writeObject(message);
      message.text = "after";
      out.writeObject(message);
      out.reset();
      out.writeObject(message);
    }
    try (ObjectInputStream in = new ObjectInputStream(
        new ByteArrayInputStream(bytes.toByteArray()))) {
      Message a = (Message) in.readObject();
      Message b = (Message) in.readObject();
      Message c = (Message) in.readObject();
      System.out.println("values=" + a.text + "," + b.text + "," + c.text);
      System.out.println("a==b=" + (a == b));
      System.out.println("b==c=" + (b == c));
    }
  }
}
```

Biên dịch/chạy với Java 17 trở lên:

```bash
javac --release 17 SerializationHandleDemo.java
java SerializationHandleDemo
```

Kết quả đã kiểm thử:

```text
values=before,before,after
a==b=true
b==c=false
```

Diễn giải:

1. Lần `writeObject` đầu mã hóa `Message{text="before"}` và tạo handle.
2. Phép gán `message.text="after"` thay đổi object **trong bộ nhớ bên gửi**, không sửa bytes đã ghi.
3. Lần `writeObject` thứ hai ghi reference tới handle; `b` là cùng object với `a`, có `text="before"`.
4. `out.reset()` ghi **reset marker** và xóa bảng objects đã biết của writer. Reader gặp marker đó và cũng reset bảng handles của mình.
5. Lần thứ ba mã hóa object như mới với `text="after"`. `c` có identity khác `b`.

Không cần tạo một `ObjectInputStream` mới sau `reset()`; reader hiện tại hiểu marker trong serialization protocol. `reset` cũng không xóa những object mà code reader đã giữ trong biến `a` hoặc `b`.

## 4. reset() làm gì và không làm gì?

Chữ ký: `public void reset() throws IOException`.

- Bỏ trạng thái handles của luồng đối với những objects đã ghi; các object sau marker được xử lý như chưa từng ghi trong **epoch** hiện tại.
- Ghi reset token vào stream, phối hợp với state của `ObjectInputStream` tương ứng.
- Thích hợp cho nhiều snapshot **độc lập** của cùng một graph mutable, khi muốn reader nhìn thấy trạng thái mới.
- Có thể giúp giới hạn lượng state do stream dài hạn ghi nhớ, nhưng làm tăng dung lượng do object/class descriptors cần encode lại.

**Không làm:** xóa bytes trước đó trong file, truncate, ghi lại object nếu chưa gọi `writeObject` sau reset, tự bảo vệ snapshot khỏi thread khác sửa field, xác nhận storage đã sync hoặc thực hiện transaction.

Không được gọi `reset()` **khi quá trình serialize một object đang diễn ra**, ví dụ bên trong custom `private void writeObject(ObjectOutputStream out)` của object đang được ghi. Thao tác không hợp lệ này có thể ném `IOException`. Hãy reset **giữa** các lần ghi toàn bộ graph.

So sánh:

| Lệnh | Tác động |
| --- | --- |
| `writeObject(x)` | Ghi định nghĩa hoặc back-reference. |
| `reset()` | Đánh dấu epoch mới; quên toàn bộ object handles hiện tại. |
| `flush()` | Đẩy bytes pending; **không làm mới handle**. |
| `writeUnshared(x)` | Ghi mới root x; nested graph có thể tiếp tục dùng handles cũ. |
| `close()` | Đóng stream/tài nguyên, không phải reset giữa cùng phiên giao thức. |
| `FileChannel.force(...)` | Yêu cầu đồng bộ dữ liệu lưu trữ, không liên quan handles. |

Một lỗi vận hành là tạo `new ObjectOutputStream(sameOutput)` nhiều lần lên **cùng một luồng liên tục** mà phía nhận vẫn dùng một `ObjectInputStream`. Constructor stream ghi header mới; header đột ngột ở giữa dữ liệu có thể gây `StreamCorruptedException`. Muốn nhiều snapshot trên một luồng, dùng một writer và `reset()`; muốn nhiều stream riêng thì cần ranh giới/reader riêng.

## 5. writeUnshared: root mới nhưng nested object cũ

`writeUnshared(root)` không phát back-reference tới chính **root** của lời gọi đó, nhưng các object con đã được ghi vẫn có thể được tham chiếu qua handles. Vì vậy nó **không phải deep copy**, cũng không bảo đảm snapshot của toàn graph có các field mới nhất.

Tạo file `WriteUnsharedDemo.java`:

```java
import java.io.*;

public class WriteUnsharedDemo {
  static class Item implements Serializable {
    private static final long serialVersionUID = 1L;
    String value;
    Item(String value) { this.value = value; }
  }
  static class Wrapper implements Serializable {
    private static final long serialVersionUID = 1L;
    String label;
    Item item;
    Wrapper(String label, Item item) { this.label=label; this.item=item; }
  }
  public static void main(String[] args) throws Exception {
    Wrapper w = new Wrapper("one", new Item("red"));
    ByteArrayOutputStream bytes = new ByteArrayOutputStream();
    try (ObjectOutputStream out = new ObjectOutputStream(bytes)) {
      out.writeObject(w);
      w.label="two";
      w.item.value="blue";
      out.writeUnshared(w);
      out.writeObject(w);
    }
    try (ObjectInputStream in = new ObjectInputStream(
        new ByteArrayInputStream(bytes.toByteArray()))) {
      Wrapper a=(Wrapper)in.readObject();
      Wrapper b=(Wrapper)in.readUnshared();
      Wrapper c=(Wrapper)in.readObject();
      System.out.println("labels="+a.label+","+b.label+","+c.label);
      System.out.println("nested="+a.item.value+","+b.item.value);
      System.out.println("a==b="+(a==b));
      System.out.println("a==c="+(a==c));
      System.out.println("nested-shared="+(a.item==b.item));
    }
  }
}
```

```bash
javac --release 17 WriteUnsharedDemo.java
java WriteUnsharedDemo
```

Kết quả kiểm thử:

```text
labels=one,two,one
nested=red,red
a==b=false
a==c=true
nested-shared=true
```

Lần đầu lưu root `Wrapper` và child `Item`. Sau khi thay đổi root thành "two" và child thành "blue", `writeUnshared(w)` ghi một **root mới** nhưng child vẫn có thể trỏ về `Item` cũ với "red". Lần `writeObject(w)` tiếp theo vẫn có thể tham chiếu root ban đầu (`a==c`). Muốn toàn graph hiện trạng được ghi lại, `reset(); writeObject(w)` rõ nghĩa hơn.

`ObjectInputStream.readUnshared()` không dùng như một phiên bản “tốt hơn” của `readObject()`: nếu entry cần đọc là **back-reference** thì `readUnshared` ném `ObjectStreamException`. Các cơ chế class như `readResolve` và đối tượng đặc biệt có thể tạo thêm ngoại lệ về identity; không suy ra mọi nested reference đều được clone.

## 6. Chu kỳ reset và bộ nhớ

Một stream tồn tại lâu và ghi nhiều object mới có thể làm handle table của writer/reader tăng, gây overhead và giữ references. Có thể đặt ranh giới giữa các batch:

```java
// Snippet minh họa; out và makeMessage(i) do ứng dụng định nghĩa.
for (int i = 0; i < 10_000; i++) {
    out.writeObject(makeMessage(i));
    if ((i + 1) % 1_000 == 0) out.reset();
}
```

Mốc 1.000 chỉ để minh họa; chọn theo kích thước graph, heap, throughput, yêu cầu identity, và benchmark thực tế. Reset **quá dày** khiến nhiều bytes phải serialize lại, có thể giảm hiệu năng. Reset **quá ít** làm state handles phình ra. Nếu receiver cần định danh một thực thể xuyên nhiều snapshots, hãy truyền **business ID/version**; đừng dựa vào Java object handle luôn giữ nguyên.

## 7. Snapshot nhất quán và ứng dụng thực tế

Cache handles chỉ là một phần bài toán. Nếu thread khác sửa graph **trong lúc** serialization, stream có thể chứa tổ hợp fields không hợp lệ. `Serializable` không có nghĩa tự động thread-safe, và `reset` không biến quá trình ghi thành transaction.

Giải pháp nên cân nhắc:

- Tạo immutable DTO snapshot bên trong lock hoặc giao dịch nghiệp vụ rồi serialize snapshot.
- Dùng **một owner** cho `ObjectOutputStream`, phối hợp các producers qua hàng đợi; tránh xen kẽ `writeObject`, `reset`, `flush` giữa nhiều threads.
- Định nghĩa rõ version/sequence khi gửi object liên tục. `ObjectOutputStream` không tự sinh delta hay application acknowledgement.
- Xử lý `IOException`, EOF và hỏng stream; không đoán peer đã xử lý thành công chỉ vì lệnh local `writeObject` trả về.
- Nếu dữ liệu phải sống sót sau mất điện, `flush/reset` không thay thế file sync và giao thức recovery.
- Tránh deserialize dữ liệu không tin cậy một cách tùy ý. Nếu buộc dùng, kiểm soát class được phép, giới hạn chiều sâu/bytes/references bằng `ObjectInputFilter` và chọn giao thức có hợp đồng rõ ràng.

Khi cần lưu trữ lâu dài, tương thích đa ngôn ngữ hoặc nâng cấp schema thường xuyên, DTO cùng định dạng như JSON/CBOR/Protobuf hoặc database có thể phù hợp hơn native Java Serialization.

## 8. Sai lầm phổ biến

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Mutate x rồi `writeObject(x)` lại | Reader thấy state cũ | Reset trước snapshot mới hoặc gửi object/version riêng |
| Gọi `flush()` để cập nhật field | Handle table không thay đổi | Phân biệt byte buffering với object identity |
| Dùng `writeUnshared` làm deep copy | Nested fields vẫn cũ | `reset + writeObject` cho graph mới |
| Dùng `readUnshared` cho back-reference | `ObjectStreamException` | Ghép contract writer/reader |
| Gọi reset trong custom `writeObject` | `IOException` | Reset giữa các graph |
| Tạo nhiều writer trên cùng stream liên tục | Stream header xuất hiện giữa luồng | Một writer + reset hoặc stream độc lập |
| Quên reset với stream sống lâu | Áp lực bộ nhớ | Chọn batch/epoch có đo đạc |
| Reset liên tục vô cớ | Tăng kích thước và công encode | Chọn policy theo workload |
| Dùng `serialVersionUID` làm object version | Không theo dõi mutation | Version/sequence nghiệp vụ |
| Serialize graph đang bị thread khác sửa | Snapshot không nhất quán | Immutable DTO, ownership, đồng bộ |
| Coi reset là flush xuống đĩa | Sai mức durability | Storage sync/transaction phù hợp |

## 9. Tự kiểm tra

**Vì sao lần `writeObject` thứ hai có thể không ghi fields đã đổi?** Vì root đã có handle, writer có thể chỉ gửi back-reference.

**Hai lần `readObject()` có thể trả cùng object không?** Có, nếu lần sau đọc back-reference.

**Reset có xóa byte cũ hoặc làm reader mất các references trước đó không?** Không; reset thay trạng thái lookup handles của **đoạn stream tiếp theo**, không xóa đối tượng ứng dụng đang giữ.

**Reset có làm mới cả graph?** Nó xóa state handles của stream, nên graph ở lần `writeObject` sau được xử lý như mới, miễn không có mutation/race đồng thời hoặc cơ chế tùy biến can thiệp.

**`writeUnshared(root)` có sao chép sâu graph không?** Không. Root mới; child vẫn có thể được tham chiếu từ handle cũ.

**Lúc nào không nên dùng native Java Serialization?** Khi dữ liệu đầu vào không tin cậy hoặc yêu cầu định dạng lưu trữ/giao tiếp bền vững, đa ngôn ngữ, dễ versioning.

## Tài liệu chính thức

- [Java SE 21 — ObjectOutputStream](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/ObjectOutputStream.html)
- [Java SE 21 — ObjectInputStream](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/ObjectInputStream.html)
- [Java Object Serialization Specification — Output](https://docs.oracle.com/en/java/javase/21/docs/specs/serialization/output.html)
- [Java Object Serialization Specification — Input](https://docs.oracle.com/en/java/javase/21/docs/specs/serialization/input.html)
- [Java SE 21 — ObjectInputFilter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/ObjectInputFilter.html)

**Kết luận:** `ObjectOutputStream` nhớ **identity của object đã ghi**, không tự theo dõi state. `reset` tạo epoch mới để ghi lại object graph; `writeUnshared` chỉ bảo đảm root mới; `flush` không thay đổi handle cache.