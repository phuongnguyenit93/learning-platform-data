# Kiểm tra bất biến sau khi khôi phục đối tượng trong Java Serialization

## 1. Tại sao phải kiểm tra bất biến *sau* deserialization?

Một **bất biến (invariant)** là điều kiện luôn phải đúng với một đối tượng hợp lệ trong suốt vòng đời sử dụng. Ví dụ:

- Khoảng số phải thỏa `0 <= start <= end`.
- Tài khoản không thể có mã định danh `null` hoặc rỗng.
- Danh sách thành viên phải có số phần tử bằng `expectedCount`; không có phần tử `null`.
- Một lịch hẹn phải có `startTime` trước `endTime`.
- Một graph gồm nhiều đối tượng phải giữ đúng quan hệ giữa cha, con và các tham chiếu ngược.
- Collection nội bộ không được bị sửa từ bên ngoài nếu hợp đồng class yêu cầu bất biến.

**Serialization** biến trạng thái đối tượng thành byte stream. **Deserialization** qua `ObjectInputStream.readObject()` dựng lại đối tượng từ stream đó. Điểm dễ bỏ sót: với class chỉ triển khai `Serializable`, việc khôi phục thông thường **không gọi constructor của chính class Serializable**, nên kiểm tra bất biến chỉ có ở constructor có thể bị bỏ qua.

Ví dụ, constructor bảo đảm `start <= end` nhưng một stream cũ, file hỏng hoặc stream cố tình sửa có thể mang `start=20` và `end=10`. Nếu ứng dụng chấp nhận dữ liệu mà không kiểm tra, nó sẽ đưa **đối tượng có trạng thái không hợp lệ** vào logic hệ thống.

Đây là lý do Java cung cấp các điểm kiểm tra như `private readObject(...)`, `ObjectInputValidation.validateObject()`, `readObjectNoData()`, cùng các chiến lược cấu trúc như **serialization proxy** và **serializable record**.

Mục tiêu của bài: biết **bất biến nào cần kiểm tra, kiểm tra khi nào, ném lỗi gì, và vì sao một số kiểm tra cần chờ toàn bộ object graph khôi phục xong**.

## 2. Deserialization diễn ra như thế nào?

Với class Serializable thông thường:

~~~text
ObjectInputStream.readObject()
            |
            v
Đọc class descriptor / trạng thái trong stream
            |
            v
Tạo đối tượng để khôi phục (KHÔNG gọi constructor Serializable class)
            |
            v
Khôi phục các field; nếu có private readObject,
thực thi readObject và defaultReadObject/readFields nếu dùng
            |
            v
Hoàn tất đồ thị đối tượng đang được đọc
            |
            v
Thực hiện ObjectInputValidation đã đăng ký (nếu có)
            |
            v
Trả đối tượng hợp lệ cho caller hoặc ném exception
~~~

Sơ đồ đơn giản hóa, không thể hiện mọi chi tiết handle, back-reference, `readResolve`, inheritance và exception. Nhưng nó nhấn mạnh:

1. **Constructor là cổng kiểm tra cho đối tượng tạo bằng `new`, chưa đủ cho deserialization Serializable**.
2. `defaultReadObject()` phục hồi field non-static/non-transient theo cơ chế mặc định; việc đó **không tự gọi validator tùy biến của class**.
3. `readObject()` là hook để kiểm tra **trạng thái cục bộ ngay sau khi field của class được khôi phục**.
4. `ObjectInputValidation` là hook bổ sung khi kiểm tra cần **đợi toàn bộ graph đã khôi phục** trước khi `readObject()` cấp cao trả về.
5. Nếu kiểm tra thất bại, nên **từ chối stream bằng `InvalidObjectException`** thay vì cố âm thầm dùng object sai.

### Vì sao constructor của Serializable không được gọi?

Java Object Serialization có cơ chế dựng lại field từ stream. Constructor no-arg của **superclass đầu tiên không triển khai Serializable** có thể được gọi theo quy tắc serialization, nhưng constructor của class Serializable sẽ không được chạy như khi gọi `new` thông thường.

Do đó các câu lệnh sau:

~~~java
public Range(int start, int end) {
    if (start > end) throw new IllegalArgumentException();
    this.start = start;
    this.end = end;
}
~~~

là **mã minh họa**, chỉ bảo vệ đường tạo object qua constructor. Nó không đủ chứng minh mọi object `Range` do `ObjectInputStream.readObject()` trả về đều hợp lệ.

**Ngoại lệ quan trọng:** Serializable **record** trong Java 17 được khôi phục theo cơ chế đặc thù có gọi **canonical constructor**; xem mục 10. Không nên áp dụng máy móc quy tắc constructor thông thường của Serializable class cho record.

## 3. Xác định bất biến trước khi chọn hook

Có thể chia điều kiện cần kiểm tra thành hai nhóm.

| Nhóm | Ví dụ | Vị trí kiểm tra phù hợp |
|---|---|---|
| **Bất biến cục bộ** của một đối tượng | `start >= 0` và `start <= end`, ID khác `null` | Trong `readObject` ngay sau `defaultReadObject` |
| **Bất biến toàn graph / liên đối tượng** | Parent-child links nhất quán, số lượng member bằng tổng dữ liệu sau khôi phục | `ObjectInputValidation` đăng ký từ `readObject` |
| **Đầu vào tùy biến theo định dạng** | Hai field được ghi riêng trong `writeObject` | Trong `readObject` sau khi đọc đủ custom data |
| **Luồng cũ/thiếu dữ liệu cho class** | Class được thêm vào hierarchy nhưng stream không có data cho nó | `readObjectNoData`, khôi phục trạng thái an toàn hoặc từ chối |
| **Đối tượng bất biến có constructor nghiêm ngặt** | Value object với field final, defensive copy | Serialization proxy hoặc record, tùy hợp đồng |

**Phạm vi bất biến** quyết định thời điểm kiểm tra:

- Không được dùng validator toàn graph để thay thế mọi **kiểm tra cục bộ sớm**, nếu trạng thái cục bộ nguy hiểm có thể bị dùng trong lúc graph còn đang dựng.
- Không được áp dụng một kiểm tra quan hệ liên đối tượng **quá sớm** nếu đối tượng liên quan vẫn chưa khôi phục hết hoặc có cycle/back-reference.
- Cả hai loại đều cần tránh phát sinh **side effect không thể hoàn tác** trong lúc object còn chưa được chứng thực hợp lệ.

## 4. Hook private readObject: kiểm tra field ngay sau khôi phục

Một class Serializable có thể định nghĩa phương thức đúng chữ ký:

~~~java
private void readObject(ObjectInputStream in)
        throws IOException, ClassNotFoundException {
    in.defaultReadObject();
    // Kiểm tra các field vừa khôi phục.
}
~~~

Các lưu ý thiết yếu:

- Phương thức phải **private**, **non-static**, trả `void` và nhận `ObjectInputStream`. Không phải override public method từ interface.
- `in.defaultReadObject()` nạp các field có thể serialize của class theo tên. Nếu class có format custom, `readObject()` có thể dùng `readFields()` hoặc đọc các giá trị tùy biến theo đúng thứ tự được ghi.
- Trong `readObject()` tùy biến, **không gọi `defaultReadObject()` và `readFields()` để đọc cùng dữ liệu hai lần**.
- Kiểm tra sau khi đã có đủ dữ liệu cần thiết; nếu sai, ném `InvalidObjectException`.
- Không nuốt `IOException`/`ClassNotFoundException` và trả về object có trạng thái chưa rõ.

### Ví dụ bất biến: khoảng số không âm

~~~java
final class Range implements Serializable {
    private static final long serialVersionUID = 1L;

    private int start;
    private int end;

    Range(int start, int end) {
        if (start < 0 || end < start) {
            throw new IllegalArgumentException("Invalid range");
        }
        this.start = start;
        this.end = end;
    }

    private void readObject(ObjectInputStream in)
            throws IOException, ClassNotFoundException {
        in.defaultReadObject();

        if (start < 0 || end < start) {
            throw new InvalidObjectException("Invalid range");
        }
    }
}
~~~

Đây là **mã minh họa ở mức class**, cần các import `java.io.*`. Constructor bảo vệ khi tạo bằng `new`, còn `readObject` bảo vệ khi khôi phục field trực tiếp từ stream.

Tại sao `InvalidObjectException` tốt hơn `IllegalArgumentException`? Vì nó là loại `ObjectStreamException`/`IOException` chuyên dùng khi đối tượng khôi phục **không đạt kiểm tra hợp lệ**, giúp caller xác định lỗi deserialization một cách rõ ràng.

**Không sửa âm thầm `end = start` chỉ để che dữ liệu hỏng** nếu contract không cho phép điều đó. Nếu bài toán thực sự có chính sách migrate/normalize dữ liệu cũ, cần quy tắc chuyển đổi tường minh, không được biến mọi invalid stream thành một object trông có vẻ hợp lệ.

## 5. Vì sao ObjectInputValidation cần thiết cho object graph?

Trong các graph có **tham chiếu vòng/cross-reference**, việc đọc field của một object chưa có nghĩa mọi object được tham chiếu đã hoàn toàn thiết lập trạng thái. Có thể có child trỏ về parent, hoặc nhiều phần cùng tham chiếu một object trong lúc nó còn đang deserialized.

Đối với quan hệ như `parent.children.contains(child)` và `child.parent == parent`, kiểm tra trong `parent.readObject()` có thể quá sớm trong một số kiểu graph, hoặc gây những hoạt động phụ nguy hiểm.

Java cung cấp:

~~~java
public interface ObjectInputValidation {
    void validateObject() throws InvalidObjectException;
}
~~~

và `ObjectInputStream.registerValidation(ObjectInputValidation obj, int priority)` để đăng ký callback **trong readObject của một class khi stream đang đọc object**. Callback sẽ chạy **sau khi object graph được khôi phục**, nhưng **trước khi đối tượng được trả cho caller** của lời đọc tương ứng.

Cách dùng khái niệm:

~~~java
private void readObject(ObjectInputStream in)
        throws IOException, ClassNotFoundException {
    in.defaultReadObject();
    in.registerValidation(this, 0);
}

@Override
public void validateObject() throws InvalidObjectException {
    if (!graphRelationshipIsValid()) {
        throw new InvalidObjectException("Inconsistent object graph");
    }
}
~~~

Đây là **mã minh họa**: class phải implements `Serializable, ObjectInputValidation`; phương thức `graphRelationshipIsValid()` là logic domain cần triển khai, không phải API JDK.

### Priority của validation

`registerValidation(obj, priority)` nhận số nguyên ưu tiên:

- **Priority lớn hơn chạy trước** priority nhỏ hơn.
- Với **cùng priority**, thứ tự callback **không xác định**.
- Dùng `0` khi không có yêu cầu thứ tự.
- Callback có thể ném `InvalidObjectException`; khi kiểm tra không đạt, việc đọc object sẽ thất bại.

**Không thiết kế bất biến dựa vào thứ tự callback trong cùng priority**. Trong một callback, kiểm tra tất cả điều kiện mà mình chịu trách nhiệm; không giả định callback khác đã sửa chữa dữ liệu trước đó nếu không có dependency có chủ đích.

### Khi nào được registerValidation?

Chỉ đăng ký đúng khi `ObjectInputStream` đang trong giai đoạn deserialization phù hợp (thông thường từ `readObject` của class). Gọi `registerValidation` ngoài ngữ cảnh đó có thể ném `NotActiveException`. Nếu đối tượng callback `null`, Javadoc quy định `InvalidObjectException`.

**Không tự gọi `validateObject()` của các class khác trong lúc graph đang dựng** để "kiểm tra sớm" khi chưa biết trạng thái của các tham chiếu liên quan.

## 6. Chương trình Java 17+ hoàn chỉnh: hai cách từ chối object sai

Ví dụ này kiểm thử:

1. `Range` kiểm tra cục bộ trong `readObject`.
2. `Roster` kiểm tra trạng thái sau khi toàn graph được restored qua `ObjectInputValidation`.
3. Cả object hợp lệ và object có trạng thái hỏng sẽ được serialize thành byte[] rồi thử deserialization.
4. Các câu lệnh cố ý làm hỏng field chỉ nằm trong **outer demo class** để tạo test data; đó không phải phương pháp sửa state trong production.

**Tệp: `InvariantDemo.java`**

~~~java
import java.io.*;
import java.util.*;

public class InvariantDemo {
    static final class Range implements Serializable {
        private static final long serialVersionUID = 1L;
        private int start;
        private int end;

        Range(int start, int end) {
            if (start < 0 || end < start) {
                throw new IllegalArgumentException("Invalid range");
            }
            this.start = start;
            this.end = end;
        }

        private void readObject(ObjectInputStream in)
                throws IOException, ClassNotFoundException {
            in.defaultReadObject();
            if (start < 0 || end < start) {
                throw new InvalidObjectException("Invalid range");
            }
        }

        @Override
        public String toString() {
            return start + ".." + end;
        }
    }

    static final class Roster
            implements Serializable, ObjectInputValidation {
        private static final long serialVersionUID = 1L;
        private List<String> names;
        private int expectedCount;

        Roster(List<String> names) {
            this.names = new ArrayList<>(names);
            this.expectedCount = names.size();
        }

        private void readObject(ObjectInputStream in)
                throws IOException, ClassNotFoundException {
            in.defaultReadObject();
            in.registerValidation(this, 0);
        }

        @Override
        public void validateObject() throws InvalidObjectException {
            if (names == null || names.size() != expectedCount) {
                throw new InvalidObjectException("Invalid roster count");
            }
            for (String name : names) {
                if (name == null || name.isBlank()) {
                    throw new InvalidObjectException("Invalid roster member");
                }
            }
            names = List.copyOf(names);
        }

        @Override
        public String toString() {
            return names.toString();
        }
    }

    static byte[] save(Object object) throws IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (ObjectOutputStream out = new ObjectOutputStream(bytes)) {
            out.writeObject(object);
        }
        return bytes.toByteArray();
    }

    static Object load(byte[] bytes)
            throws IOException, ClassNotFoundException {
        try (ObjectInputStream in = new ObjectInputStream(
                new ByteArrayInputStream(bytes))) {
            return in.readObject();
        }
    }

    public static void main(String[] args) throws Exception {
        Range good = (Range) load(save(new Range(4, 9)));
        System.out.println("range=" + good);

        Range broken = new Range(4, 9);
        broken.end = 1; // Chỉ outer test cố ý phá private state.
        try {
            load(save(broken));
            System.out.println("rangeRejected=false");
        } catch (InvalidObjectException expected) {
            System.out.println("rangeRejected=true");
        }

        Roster roster = (Roster) load(
                save(new Roster(List.of("Ada", "Bob"))));
        System.out.println("roster=" + roster);

        Roster badRoster = new Roster(List.of("Ada", "Bob"));
        badRoster.expectedCount = 3; // Test-only malformed state.
        try {
            load(save(badRoster));
            System.out.println("rosterRejected=false");
        } catch (InvalidObjectException expected) {
            System.out.println("rosterRejected=true");
        }
    }
}
~~~

Chạy với JDK 17 trở lên:

~~~bash
javac InvariantDemo.java
java InvariantDemo
~~~

**Stdout đã kiểm tra trên JDK:**

~~~text
range=4..9
rangeRejected=true
roster=[Ada, Bob]
rosterRejected=true
~~~

Giải thích:

- `new Range(4,9)` hợp lệ; deserialization chạy `Range.readObject` và giữ bất biến nên in `4..9`.
- `broken.end = 1` chỉ có thể thực hiện vì `Range` là nested class của `InvariantDemo`; enclosing class được quyền truy cập private field của nested class. Đây là cách **cố tình tạo serialized fixture không hợp lệ trong bài test**, không phải field setter trong API production. Constructor ban đầu vẫn kiểm tra hợp lệ, nhưng serialized bytes chứa state đã bị thay đổi.
- Khi `load(save(broken))`, `defaultReadObject` nạp `start=4`, `end=1` và validator ném `InvalidObjectException`; kết quả `rangeRejected=true`.
- `Roster` hợp lệ có 2 tên và `expectedCount=2`. Khi deserialization hoàn tất graph, `validateObject` kiểm tra count và từng tên, rồi dùng `List.copyOf` để có danh sách không thể sửa qua API List.
- `badRoster.expectedCount=3` khiến dữ liệu serializable không phù hợp với danh sách, do đó callback từ chối và in `rosterRejected=true`.

**Lưu ý về chất lượng demo:** Trong ví dụ, constructor `Roster` chỉ sao chép danh sách mà chưa kiểm tra từng tên không null/blank, để giữ trọng tâm hiển thị callback sau deserialization. **Một class production phải kiểm tra bất biến ở tất cả đường tạo object**, gồm constructor, factory, setter hoặc mutation API, và đường deserialization. Có thể tái sử dụng một hàm validation domain chung thay vì lặp quy tắc phân tán.

### Vì sao không cần sửa từng byte serialized stream để thử invalid?

Unit test muốn kiểm tra invariant phải cung cấp stream chứa state xấu. Cách làm hỏng private field ở một fixture **cùng nest** như demo dễ kiểm soát hơn việc sửa byte bằng magic offset trong serialized binary. Không dùng offset cố định giả định format Java Serialization của một class luôn giống nhau giữa các phiên bản.

## 7. Kiểm tra null, phạm vi, collection và object liên kết

Các nhóm bất biến thường cần kiểm tra:

| Đối tượng | Bất biến | Lỗi có thể có từ stream |
|---|---|---|
| `Range` | `start >= 0`, `end >= start` | Start âm, end nhỏ hơn start |
| `Account` | `accountId != null`, non-blank | Null hoặc empty ID |
| `Order` | `items != null`, item hợp lệ | Missing field hoặc null list |
| `Roster` | `expectedCount == names.size()` | Count không khớp |
| `Schedule` | `start.isBefore(end)` | Thời gian đảo ngược hoặc null |
| `GraphNode` | Quan hệ liên kết parent-child khớp | Back-reference không nhất quán |
| `CacheConfig` | Timeout dương, memory budget trong khoảng | Field âm hoặc quá lớn |

Không đủ nếu chỉ kiểm tra null của container. Phải kiểm tra **từng phần tử** và những ràng buộc liên quan đến tổng số lượng/uniqueness:

~~~java
if (members == null) {
    throw new InvalidObjectException("members missing");
}
for (Member member : members) {
    if (member == null || member.id() == null) {
        throw new InvalidObjectException("Invalid member");
    }
}
~~~

Đây là mã minh họa: `Member` là type ứng dụng tự định nghĩa có phương thức `id()`, không phải một class JDK.

### Kiểm tra số học tránh overflow

Ví dụ bất biến tổng tiền không âm:

~~~java
long total;
try {
    total = Math.addExact(unitPrice, tax);
} catch (ArithmeticException overflow) {
    throw new InvalidObjectException("Total overflow");
}
if (unitPrice < 0 || tax < 0 || total > maxAllowed) {
    throw new InvalidObjectException("Invalid total");
}
~~~

Các biến long là dữ liệu đã có từ object; đoạn code chỉ minh họa. Không tính `int sum = a + b` rồi kiểm tra `sum >= 0` mà không nghĩ tới **integer overflow**. Với dữ liệu do stream cung cấp, kích thước mảng, độ dài danh sách và số lượng nested objects cũng cần giới hạn ở nhiều lớp.

### Không tin trường derived hoặc cached state

Nếu một class serialize `items` và cả `cachedTotal`, stream có thể cung cấp `cachedTotal` không khớp với items. Hai hướng:

- **Không serialize field derived:** đánh dấu `transient` và **tái tạo** nó từ dữ liệu nguồn sau khi khôi phục.
- Nếu metadata cache cần lưu, **đối chiếu lại** với dữ liệu thực trước khi dùng hoặc bỏ cache rồi recompute theo chính sách.

Không dùng `cachedTotal` chưa xác thực để cấp phát memory, tính phí hoặc cấp quyền.

## 8. Khi graph có cycle và aliasing

Một đối tượng có thể tham chiếu lặp cùng instance ở nhiều vị trí, và các đối tượng có thể có vòng liên kết:

~~~text
Parent P ------> Child C
     ^                |
     |                |
     +----------------+
      C.parent == P
~~~

Trong `P.readObject`, `C` có thể chưa được xây dựng đầy đủ ở mọi thời điểm mà code tùy biến chạy, nhất là khi graph có cycle/back-reference. Vì vậy kiểm tra `C.parent == P` hoặc `P.children.contains(C)` thường phù hợp với **`ObjectInputValidation` sau graph hoàn tất** hơn là eager callback quá sớm.

Ví dụ pseudocode:

~~~java
private void readObject(ObjectInputStream in)
        throws IOException, ClassNotFoundException {
    in.defaultReadObject();
    in.registerValidation(this, 0);
}

@Override
public void validateObject() throws InvalidObjectException {
    if (children == null) {
        throw new InvalidObjectException("Missing children");
    }
    for (Node child : children) {
        if (child == null || child.parent != this) {
            throw new InvalidObjectException("Broken bidirectional link");
        }
    }
}
~~~

Đây là **pseudocode không độc lập**: `Node`, `children` và field `parent` thuộc mô hình riêng của ứng dụng. Nếu dùng `List.copyOf(children)`, phải cẩn thận aliasing và tránh biến mutable object graph sang dạng không nhất quán; một bản sao list không tự clone các `Node` bên trong.

### Không nên gọi phương thức overridable của this khi đang deserialize

Trong `readObject`, object có thể ở trạng thái chưa hoàn tất. Nếu gọi method có thể override, subclass có thể chạy trên field chưa khởi tạo và làm rò rỉ tham chiếu `this`. Nên dùng validation nội bộ, private/final methods với tác động hạn chế và tránh đăng ký `this` vào global registry, dispatch event, khởi chạy thread hoặc gọi external callbacks trước khi hợp lệ.

## 9. Dữ liệu thiếu khi class tiến hóa: readFields và readObjectNoData

Serialized data có thể được tạo bởi một phiên bản class cũ. Trong Java Serialization, `serialVersionUID` hỗ trợ nhận diện phiên bản tương thích, **không tự bảo đảm bất biến domain**.

### 9.1. Field mới không có trong stream

Nếu phiên bản mới thêm `requiredName` nhưng stream cũ không có field, cách đọc mặc định có thể đặt field tham chiếu thành `null`, primitive thành 0/false. Chương trình phải quyết định có được migrate hợp lệ hay không.

Thay vì `defaultReadObject()`, có thể dùng `ObjectInputStream.GetField`:

~~~java
private void readObject(ObjectInputStream in)
        throws IOException, ClassNotFoundException {
    ObjectInputStream.GetField fields = in.readFields();
    if (fields.defaulted("name")) {
        throw new InvalidObjectException("Required name missing");
    }

    String name = (String) fields.get("name", null);
    if (name == null || name.isBlank()) {
        throw new InvalidObjectException("Invalid name");
    }
    this.name = name;
}
~~~

Đoạn này minh họa một class Serializable có field `String name`; `readFields()` và `defaultReadObject()` là **hai cách thay thế**, không gọi cả hai để nạp cùng một dữ liệu. Dùng `defaulted("name")` khi cần phân biệt field thực sự vắng mặt khỏi field có giá trị mặc định. `serialVersionUID` vẫn phải phù hợp chính sách tương thích.

### 9.2. readObjectNoData()

Một class Serializable có thể khai báo:

~~~java
private void readObjectNoData() throws ObjectStreamException {
    throw new InvalidObjectException(
            "Serialized stream lacks required class data");
}
~~~

Hook được dùng trong tình huống stream **không có dữ liệu tương ứng cho class trong hierarchy** (ví dụ thay đổi hierarchy tương thích, hoặc nguồn không hoàn chỉnh/bất thường), khác với việc một field đơn lẻ của class bị thiếu.

Một số class có thể tự tái lập giá trị mặc định hợp lệ tại hook này; nếu không thể đảm bảo bất biến, **từ chối** là lựa chọn đúng. Không tự phỏng đoán giá trị của thông tin bảo mật, giá tiền, quyền truy cập hoặc định danh bị thiếu.

## 10. Object bất biến: defensive copy, serialization proxy và record

### 10.1. Không để dữ liệu mutable phá bất biến về sau

Kiểm tra `List` trong validator là một bước; nhưng nếu object giữ một tham chiếu đến collection mutable có thể bị phần khác sửa, bất biến sẽ bị phá sau khi deserialize.

Ví dụ:

~~~java
private void readObject(ObjectInputStream in)
        throws IOException, ClassNotFoundException {
    in.defaultReadObject();
    if (names == null || names.stream().anyMatch(
            n -> n == null || n.isBlank())) {
        throw new InvalidObjectException("Invalid names");
    }
    names = List.copyOf(names);
}
~~~

Đây là minh họa. `List.copyOf` trả danh sách không thể bị chỉnh sửa qua API List, và giúp tạo **defensive snapshot** của collection. Nhưng các **phần tử mutable** bên trong vẫn cần được kiểm soát: `List.copyOf` là **shallow copy**, không tự clone sâu object graph.

Với class Serializable có các field `final` và muốn giữ representation invariant nghiêm ngặt, việc tùy biến trường trong `readObject` không phải lúc nào là cách tốt nhất. Có thể chọn serialization proxy.

### 10.2. Serialization proxy pattern

Ý tưởng: bản thân class quan trọng không được deserialize trực tiếp. Nó serialize một **proxy** chỉ chứa dữ liệu được phép; `readResolve` của proxy tạo object mới **qua constructor/factory có kiểm tra bất biến**.

~~~text
ValueObject hợp lệ
    |
    | writeReplace()
    v
SerializationProxy(data primitives / stable values)
    |
    | byte stream
    v
SerializationProxy được deserialize
    |
    | readResolve() -> new ValueObject(validated data)
    v
ValueObject hợp lệ hoặc InvalidObjectException
~~~

Khi thiết kế theo pattern này, method `readObject` của class gốc thường **luôn ném InvalidObjectException** để cấm khôi phục trực tiếp một serialized form không qua proxy. `readResolve` của proxy xử lý đối tượng thay thế; đảm bảo mọi đường tạo object logic đi qua constructor/factory. Mẫu này có overhead và giới hạn riêng với subclass/cycle, nên cần thiết kế theo domain, không dùng bừa cho mọi class.

### 10.3. Serializable record trên Java 17

Record Serializable được khôi phục **bằng canonical constructor** theo cơ chế serialization đặc biệt. Vì vậy kiểm tra trong canonical constructor có thể dùng làm cổng xác thực ngay khi khôi phục.

~~~java
record Score(int value) implements Serializable {
    Score {
        if (value < 0 || value > 100) {
            throw new IllegalArgumentException("Score out of range");
        }
    }
}
~~~

Đây là **đoạn class minh họa**, cần `java.io.Serializable`. Nếu muốn trả lỗi domain ở cấp deserialization, caller cần hiểu exception có thể được bọc theo cơ chế serialization của record và xử lý thích hợp, không giả định hook `readObject` thông thường được gọi cho record. Với record, những phương thức serialization tùy biến như `readObject`/`writeObject` có semantics khác class Serializable truyền thống; hãy tham khảo đặc tả record serialization thay vì chép nguyên mẫu class thường.

## 11. Đừng xem invariant validation là giải pháp an toàn duy nhất

`InvalidObjectException` chặn một **object state không hợp lệ** trước khi object đó được trả cho caller. Nhưng nó không biến việc deserialize byte không tin cậy thành an toàn:

- **Gadget chain:** trong lúc deserialize, code các type đã được chọn có thể chạy **trước khi validator của class đích hoàn tất**.
- **DoS / object bomb:** graph có thể rất sâu, có quá nhiều đối tượng, mảng rất lớn hoặc tiêu tốn CPU trước lúc được kiểm tra.
- **Side effects sớm:** các `readObject` của class con lồng nhau có thể thực hiện hành vi nguy hiểm trước callback `ObjectInputValidation`.
- **Class evolution:** type và field từ stream có thể khác những gì ứng dụng đã giả định, dù qua được `serialVersionUID`.

**Nguyên tắc:** Không nên deserialize Java native object từ nguồn không tin cậy nếu có lựa chọn format dữ liệu an toàn hơn. Nếu phải dùng Java Serialization, áp dụng **`ObjectInputFilter`** để hạn chế class/resource, xác thực nguồn, giới hạn byte/depth/reference/array, và chỉ sử dụng những class đã được kiểm toán. Filter hỗ trợ giảm bề mặt tấn công **trước/trong quá trình đọc**, còn invariant validator bảo vệ quy tắc domain **sau khi field/graph được dựng**.

### Ví dụ policy filter ở mức ý tưởng

~~~java
ObjectInputFilter filter =
        ObjectInputFilter.Config.createFilter(
                "maxdepth=10;maxrefs=200;maxarray=1000;" +
                "maxbytes=100000;com.example.model.*;!*");
in.setObjectInputFilter(filter);
Object obj = in.readObject();
~~~

Đây là **mã minh họa**: `in` là `ObjectInputStream`, package `com.example.model` chỉ là ví dụ, và filter phải cho phép **các loại thành phần cần thiết khác** theo định dạng object graph thực tế. Không copy nguyên policy vào production mà chưa kiểm tra type sẽ được khôi phục. Filter không tự xác minh field domain và không thay `InvalidObjectException`.

### Không trả một nửa object graph cho caller

Nếu validator ném lỗi, bỏ phiên đọc và byte stream theo chính sách error handling. Không lấy các object đã được đặt tạm vào global cache trong quá trình khôi phục để dùng tiếp, vì chúng có thể chứa state chưa hợp lệ. Nên tránh callback/event đăng ký ngoài hệ thống trước khi validation thành công.

## 12. Unit test bất biến trong môi trường thực tế

Chỉ kiểm tra "serialize rồi deserialize bằng đúng class hiện tại" là chưa đủ; trường hợp đó thường cho **happy path** và không phát hiện đường bỏ qua constructor.

Bộ test nên bao gồm:

1. **Round-trip hợp lệ:** serialize rồi restore thành công, dữ liệu giữ đúng invariants.
2. **Field số sai:** start âm, end nhỏ hơn start, thời gian đảo ngược.
3. **Field nullable:** null name/ID/collection, phần tử null/blank, dữ liệu thiếu.
4. **Cross-field:** tổng không khớp, range chồng lấn trái quy tắc, enum kết hợp không hợp lệ.
5. **Cross-object/cycle:** parent-child reference không đồng bộ hoặc aliasing bất thường.
6. **Dữ liệu phiên bản cũ:** field newly required bị thiếu; hook `readObjectNoData` khi đổi hierarchy.
7. **Object graph quá lớn:** giới hạn size/depth bằng filter/quota, không chờ tới callback.
8. **Defensive copy:** sau restore, thử sửa collection truyền ra API, bảo đảm object giữ đúng invariant.
9. **Exception chính xác:** kỳ vọng `InvalidObjectException` (hoặc lỗi hợp đồng tương ứng) cho đường invalid, không chấp nhận fallback im lặng.
10. **Resource lifecycle:** `ObjectInputStream`/underlying stream được đóng đúng khi exception, không rò rỉ file descriptor.

### Ví dụ assertion mà không lệ thuộc bytes của stream

~~~java
byte[] payload = save(new Range(4, 9));
Range restored = (Range) load(payload);
// Test restored.start == 4 && restored.end == 9.

Range malformed = new Range(4, 9);
// Chỉ code test cùng nest được phép deliberately change private field:
malformed.end = 1;

// Test kỳ vọng load(save(malformed)) ném InvalidObjectException.
~~~

Đoạn minh họa sử dụng helper và nested class của `InvariantDemo` ở mục 6, không phải code độc lập. Không nên **patch bytes ở magic offset** rồi giả định serialized binary format sẽ giống nhau ở mọi build/version. Có thể dùng fixture phiên bản cũ hoặc serialization proxy fixture để tạo nguồn dữ liệu lỗi một cách có kiểm soát.

## 13. Những lỗi phổ biến

1. **"Constructor đã validate nên deserialize luôn an toàn."** Sai với Serializable class thông thường; constructor của chính class không chạy như new.
2. **"`defaultReadObject()` tự kiểm tra tất cả bất biến."** Sai; nó chủ yếu phục hồi field mặc định.
3. **"`readObject()` phải public để Java gọi được."** Sai; hook chuẩn có chữ ký private đặc biệt.
4. **"Cứ ném `IllegalArgumentException` là đủ."** `InvalidObjectException` diễn đạt lỗi khôi phục dữ liệu rõ hơn; caller cần nhận diện đúng loại lỗi.
5. **"Chỉ check field != null."** Sai nếu còn ràng buộc phạm vi, thứ tự, uniqueness, checksum, cardinality hoặc cross-object.
6. **"Đối tượng liên kết luôn hoàn tất khi parent.readObject chạy."** Không nên giả định trong graph có cycle và back-reference.
7. **"`ObjectInputValidation` chạy ngay lúc đăng ký."** Sai; callback được thực hiện sau khi graph khôi phục theo hợp đồng.
8. **"Các callback cùng priority có thứ tự cố định."** Sai; không được đảm bảo.
9. **"Gọi `registerValidation` bất kỳ lúc nào cũng được."** Sai; chỉ được dùng trong ngữ cảnh đọc object phù hợp.
10. **"Chỉ validate một lần đủ giữ bất biến mãi mãi."** Sai nếu object có mutable fields, aliasing và setter không kiểm tra.
11. **"`List.copyOf` clone sâu toàn bộ graph."** Sai; shallow snapshot của collection, element mutable vẫn có thể thay đổi.
12. **"serialVersionUID là security check."** Sai; nó không xác thực source hay domain data.
13. **"ObjectInputFilter thay thế readObject validator."** Sai; filter chủ yếu hạn chế loại object và tài nguyên, không kiểm tra mọi quan hệ giữa field.
14. **"readObjectNoData áp dụng mỗi khi một field thiếu."** Sai; nó xử lý class data vắng trong hierarchy, khác `GetField.defaulted`.
15. **"readObject của Serializable class luôn gọi constructor."** Sai; nhưng Serializable record có cách khôi phục riêng với canonical constructor.
16. **"Thấy validate thất bại cứ sửa state rồi tiếp tục."** Nếu không có quy tắc migration rõ ràng, phải từ chối dữ liệu.
17. **"Dữ liệu đang deserialize có thể tự đăng ký vào global cache ngay."** Nguy hiểm vì object chưa được kiểm chứng.
18. **"Deserialization từ nguồn bất kỳ an toàn miễn là mình bắt IOException."** Sai; validation không chặn mọi gadget/DoS trước khi callback.

## 14. Tự kiểm tra kiến thức

**Câu 1:** Tại sao constructor `Range(int start, int end)` có kiểm tra dữ liệu nhưng một object Deserialize vẫn có thể mang `start > end`?

**Đáp án:** Cơ chế `Serializable` thường khôi phục field từ byte stream mà không gọi constructor của chính Serializable class, nên phải kiểm tra ở hook deserialization.

**Câu 2:** Trong `private readObject`, nên gọi `defaultReadObject()` trước hay sau khi kiểm tra `start` và `end`?

**Đáp án:** Trước. Field cần được phục hồi rồi mới có dữ liệu đúng để kiểm tra. Nếu không có custom format, `defaultReadObject` nạp những field serializable của class.

**Câu 3:** Khi nào dùng `ObjectInputValidation` thay vì chỉ kiểm tra ở `readObject`?

**Đáp án:** Khi bất biến phụ thuộc graph hoặc các đối tượng khác có thể chưa được khôi phục xong trong lúc `readObject` đang chạy. Đăng ký validator từ `readObject` để nhận callback sau graph được khôi phục.

**Câu 4:** Vì sao cùng priority `0` không nên dùng để sắp thứ tự hai validation phụ thuộc nhau?

**Đáp án:** Java không bảo đảm thứ tự callbacks với cùng priority. Nếu cần dependency, phải thiết kế thứ tự có chủ đích hoặc hợp nhất kiểm tra phụ thuộc vào một điểm nhất quán.

**Câu 5:** Nếu stream cũ không có field `String name` mới bắt buộc, có thể phát hiện bằng cách nào?

**Đáp án:** Có thể dùng `readFields()` và `GetField.defaulted("name")`, hoặc phát hiện giá trị null sau `defaultReadObject` tùy policy. Không tự coi null là hợp lệ nếu field là bắt buộc.

**Câu 6:** `ObjectInputFilter` có thay việc kiểm tra `expectedCount == names.size()` không?

**Đáp án:** Không. Filter giúp hạn chế class/graph/resource, còn bất biến domain cần kiểm tra ở readObject hoặc ObjectInputValidation.

**Câu 7:** Object immutable đã được khôi phục và validate list. Dùng `List.copyOf` có làm mọi thành viên bên trong immutable không?

**Đáp án:** Không. Nó tạo snapshot không sửa được của collection, nhưng các phần tử có thể vẫn mutable. Cần defensive copy sâu hoặc type bất biến cho từng phần tử nếu invariant đòi hỏi.

### Tài liệu chính thức (Java 17)

- [Serializable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Serializable.html)
- [ObjectInputStream: defaultReadObject, readFields, registerValidation, setObjectInputFilter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputStream.html)
- [ObjectInputValidation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputValidation.html)
- [InvalidObjectException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InvalidObjectException.html)
- [ObjectInputFilter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputFilter.html)
- [Java Object Serialization Specification — Object Input Classes](https://docs.oracle.com/en/java/javase/17/docs/specs/serialization/input.html)
- [Java Object Serialization Specification — Serializable Objects](https://docs.oracle.com/en/java/javase/17/docs/specs/serialization/serial-arch.html)
- [Record Serialization (Java 17)](https://docs.oracle.com/en/java/javase/17/docs/specs/serialization/serialization-records.html)
