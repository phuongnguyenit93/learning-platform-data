# Vì sao `equals(MyType)` là nạp chồng thay vì ghi đè?

## 1. Điểm quyết định là chữ ký phương thức

Mọi lớp Java đều thừa kế (trực tiếp hoặc gián tiếp) từ `java.lang.Object`. Phương thức so sánh bình đẳng mà Java công bố ở `Object` là:

```java
public boolean equals(Object obj)
```

Để **ghi đè (override)** phương thức này, lớp con phải cung cấp một phương thức có chữ ký tương ứng: tên `equals` và **tham số `Object`**. Tham số là `MyType` không tương đương với `Object`, dù `MyType` là lớp con của `Object`.

```java
class MyType {
    public boolean equals(MyType other) { // overload của equals(Object)
        return true;
    }

    @Override
    public boolean equals(Object obj) {   // override Object.equals(Object)
        return super.equals(obj);
    }
}
```

Đây chỉ là đoạn minh họa chữ ký; cách so sánh trả về `true` vô điều kiện ở `equals(MyType)` không phải cách cài đặt equality đúng cho ứng dụng.

| Cách khai báo | Quan hệ với `Object.equals(Object)` | Vì sao? |
| --- | --- | --- |
| `boolean equals(Object obj)` | **Override** | Giữ đúng tên và kiểu tham số của phương thức gốc |
| `boolean equals(MyType other)` | **Overload** | Cùng tên nhưng kiểu tham số khác |
| `boolean equals(String text)` | **Overload** | Kiểu tham số cũng khác |
| `boolean equals(Object a, Object b)` | **Overload** | Khác số lượng tham số |
| `boolean equals(Object obj, int mode)` | **Overload** | Khác danh sách tham số |

Kiểu trả về không giúp biến `equals(MyType)` thành override. Riêng khi ghi đè `Object.equals(Object)`, kiểu trả về phải tương thích với `boolean` — thực tế là `boolean`. Tương tự, đổi tên tham số từ `obj` sang `other` không làm thay đổi chữ ký.

**Lưu ý về phạm vi:** Nếu một lớp cha hoặc interface do bạn tự định nghĩa cũng khai báo `equals(MyType)`, thì phương thức `equals(MyType)` ở lớp con có thể ghi đè hoặc hiện thực hóa *phương thức riêng đó*. Nhưng nó vẫn **không** ghi đè `Object.equals(Object)`.

## 2. Vì sao Java lại gọi hai phiên bản khác nhau?

Java chọn một phương thức theo hai bước cần phân biệt:

1. **Overload resolution (lúc biên dịch):** Java nhìn vào kiểu tĩnh của biến, kiểu tĩnh của đối số và các phương thức áp dụng được để chọn chữ ký nào sẽ được gọi.
2. **Dynamic dispatch (lúc chạy):** Sau khi đã chọn chữ ký, nếu phương thức instance được ghi đè, Java chọn implementation thích hợp theo kiểu thực tế của đối tượng nhận lời gọi.

Điều quan trọng là dynamic dispatch **không tự chuyển** từ chữ ký `equals(Object)` sang một overload `equals(MyType)` chỉ vì đối tượng truyền vào đang là `MyType`.

Giả sử `a` có kiểu tĩnh `MyType`:

```java
MyType b = new MyType();
Object bAsObject = b;

a.equals(b);          // Có thể chọn equals(MyType)
a.equals(bAsObject);  // Chọn equals(Object)
((Object) a).equals(b); // Chọn equals(Object)
```

Ba biểu thức ở trên dùng chung đối tượng thực tế, nhưng **kiểu tại vị trí gọi** khác nhau. Khi `MyType` có cả hai chữ ký, lời gọi đầu ưu tiên overload nhận `MyType` vì cụ thể hơn; hai lời gọi còn lại sử dụng chữ ký `equals(Object)`.

## 3. Ví dụ lỗi: chỉ cài `equals(MyType)`

Tạo tệp `BadEqualsDemo.java`:

```java
import java.util.HashSet;
import java.util.Set;

public class BadEqualsDemo {
    static final class Item {
        private final int id;

        Item(int id) {
            this.id = id;
        }

        // Đây là overload; không ghi đè Object.equals(Object).
        public boolean equals(Item other) {
            return other != null && id == other.id;
        }
    }

    public static void main(String[] args) {
        Item a = new Item(7);
        Item b = new Item(7);
        Object bAsObject = b;

        System.out.println(a.equals(b));
        System.out.println(a.equals(bAsObject));
        System.out.println(((Object) a).equals(b));

        Set<Item> unique = new HashSet<>();
        unique.add(a);
        unique.add(b);
        System.out.println(unique.size());
    }
}
```

Chạy với JDK 17 hoặc mới hơn:

```bash
javac BadEqualsDemo.java
java BadEqualsDemo
```

Kết quả:

```text
true
false
false
2
```

Giải thích từng dòng:

- `a.equals(b)`: `b` có kiểu tĩnh `Item`, nên Java chọn overload `equals(Item)`; hai `id` bằng nhau, nhận `true`.
- `a.equals(bAsObject)`: đối số có kiểu tĩnh `Object`, nên `equals(Item)` không áp dụng. Java gọi `equals(Object)` thừa kế từ `Object`, mặc định so sánh cùng tham chiếu; kết quả `false`.
- `((Object) a).equals(b)`: kiểu tĩnh của đối tượng nhận lời gọi là `Object`, vì vậy chỉ xét chữ ký nhìn thấy qua `Object`; do `Item` chưa override `equals(Object)`, kết quả vẫn `false`.
- `HashSet` kiểm tra equality thông qua hợp đồng `equals(Object)` và `hashCode()`; hai instance riêng biệt không được coi là bằng nhau nên kích thước là `2`.

Đây là một lỗi dễ bỏ sót: kiểm thử thủ công `a.equals(b)` có thể “đạt”, trong khi `Set`, `Map` hoặc tiện ích làm việc qua `Object` lại không có cùng nhận định về bình đẳng.

**Cách tự kiểm tra với `@Override`:** Nếu thêm `@Override` ngay trước `equals(Item other)` trong ví dụ này, biên dịch sẽ báo lỗi vì phương thức đó không ghi đè phương thức nào có chữ ký phù hợp ở kiểu cha hay interface. Đây là lý do nên dùng `@Override` mỗi khi bạn *định* ghi đè.

## 4. Sửa đúng: ghi đè `equals(Object)` và `hashCode()`

Tạo tệp độc lập `GoodEqualsDemo.java`:

```java
import java.util.HashSet;
import java.util.Set;

public class GoodEqualsDemo {
    static final class Item {
        private final int id;

        Item(int id) {
            this.id = id;
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof Item other)) {
                return false;
            }
            return id == other.id;
        }

        @Override
        public int hashCode() {
            return Integer.hashCode(id);
        }
    }

    public static void main(String[] args) {
        Item a = new Item(7);
        Item b = new Item(7);
        Object bAsObject = b;

        System.out.println(a.equals(b));
        System.out.println(a.equals(bAsObject));
        System.out.println(((Object) a).equals(b));

        Set<Item> unique = new HashSet<>();
        unique.add(a);
        unique.add(b);
        System.out.println(unique.size());
    }
}
```

Biên dịch và chạy:

```bash
javac GoodEqualsDemo.java
java GoodEqualsDemo
```

Kết quả:

```text
true
true
true
1
```

Ở phiên bản đúng:

- `equals(Object)` được ghi đè thực sự. Vì vậy, dù gọi qua biến `Object`, dynamic dispatch vẫn chạy `Item.equals(Object)`.
- `this == obj` xử lý nhanh trường hợp cùng tham chiếu.
- Pattern matching cho `instanceof` (`obj instanceof Item other`, có trong Java 17) kiểm tra loại đối tượng, trả `false` cho `null` và kiểu không phù hợp, đồng thời tạo biến `other` đã ép kiểu.
- `id == other.id` là quy tắc bình đẳng theo giá trị đã được lựa chọn cho ví dụ.
- `hashCode()` dùng cùng thành phần `id`, bảo đảm hai `Item` bằng nhau có cùng mã băm. `HashSet` vì thế giữ một phần tử đại diện cho hai giá trị bằng nhau.

Vì `Item` được khai báo `final` và `id` bất biến, ví dụ tránh được những trường hợp phức tạp về bình đẳng giữa lớp cha và lớp con hoặc về mã băm thay đổi sau khi thêm vào `HashSet`. Với lớp có kế thừa, cần thiết kế quy tắc equality sao cho đối xứng và bắc cầu; không thể mặc định mọi cách dùng `instanceof` hay `getClass()` đều phù hợp.

## 5. Hệ quả đối với Collection, generics và API

Các API Java thường hoạt động qua kiểu `Object`, trực tiếp hoặc gián tiếp:

- **`HashSet` và `HashMap`:** dùng các quy tắc `equals(Object)` và `hashCode()` để nhận diện phần tử hoặc khóa bằng nhau. Một overload `equals(MyType)` không thay thế được hai phương thức hợp đồng này.
- **`Objects.equals(a, b)`:** nếu `a` không phải `null`, phương thức gọi `a.equals(b)` trên tham chiếu có kiểu `Object`; do đó lời gọi dựa vào `equals(Object)`.
- **API tổng quát dùng `Object` hoặc kiểu tham số tổng quát:** chỉ biết hợp đồng của kiểu công bố ở biên API. Overload chỉ nhận kiểu con có thể không được chọn.

Generics không biến `equals(MyType)` thành override. Ví dụ, dùng `Set<Item>` không có nghĩa Collection sẽ gọi overload `equals(Item)`; các hợp đồng equality của Java vẫn dựa vào `Object.equals(Object)`.

**Nên làm gì khi muốn so sánh theo nghiệp vụ khác với equality chung?** Dùng tên riêng thể hiện chủ đích, như `hasSameId(Item other)`, `matches(Item other)` hoặc `sameBusinessKey(Item other)`. Đừng đặt một overload `equals(MyType)` có tiêu chí khác với `equals(Object)`, vì kết quả khi gọi sẽ thay đổi khó đoán theo kiểu tĩnh của biến.

## 6. Không chỉ là đúng chữ ký: phải giữ hợp đồng `equals`

Sau khi ghi đè đúng chữ ký, implementation còn phải đáp ứng hợp đồng `Object.equals`:

| Thuộc tính | Diễn giải |
| --- | --- |
| Phản xạ (reflexive) | `x.equals(x)` phải là `true` với `x` khác `null`. |
| Đối xứng (symmetric) | `x.equals(y)` và `y.equals(x)` phải có cùng kết quả. |
| Bắc cầu (transitive) | Nếu `x` bằng `y` và `y` bằng `z`, thì `x` phải bằng `z`. |
| Nhất quán (consistent) | Khi thông tin dùng để so sánh không đổi, gọi lại phải giữ kết quả. |
| Khác `null` | `x.equals(null)` phải là `false` với `x` khác `null`. |
| Tương thích mã băm | Nếu `x.equals(y)` là `true`, `x.hashCode() == y.hashCode()` cũng phải là `true`. Chiều ngược lại không bắt buộc. |

Không dùng trường dễ thay đổi để tính `hashCode` cho đối tượng đang được lưu làm khóa trong cấu trúc băm; thay đổi mã băm có thể khiến việc tìm kiếm hoặc xóa không còn hoạt động như mong đợi.

Nếu kiểu chỉ chứa dữ liệu bất biến và equality theo từng thành phần, Java `record` có thể giúp tránh lỗi cài đặt thủ công: `record Item(int id) {}` tự tạo `equals(Object)` và `hashCode()` theo các thành phần của record. Tuy nhiên vẫn cần quyết định xem so sánh theo từng trường có đúng ngữ nghĩa nghiệp vụ hay không.

## 7. Checklist khi cài đặt `equals`

1. Dùng đúng `public boolean equals(Object obj)` và đặt `@Override` ngay trước phương thức.
2. Xác định những trường thực sự tạo nên danh tính giá trị; kiểm tra `null` và loại đối tượng phù hợp.
3. Đảm bảo phản xạ, đối xứng, bắc cầu và nhất quán; chú ý kế thừa và dữ liệu có thể thay đổi.
4. Ghi đè `hashCode()` dựa trên cùng các thành phần tạo nên equality.
5. Kiểm thử cả `a.equals(b)`, `a.equals((Object) b)`, `Objects.equals(a, b)`, cùng hành vi trong `HashSet` hoặc `HashMap`.
6. Nếu cần một kiểu so sánh khác, dùng phương thức có tên rõ ràng thay vì tạo thêm overload `equals(MyType)` khó hiểu.

**Tự kiểm tra:** Lớp `Person` chỉ có `boolean equals(Person p)`. Khi truyền hai `Person` có cùng dữ liệu vào `HashSet<Person>`, bộ sưu tập có bắt buộc coi chúng là một phần tử không? **Không.** `equals(Person)` là overload; nó không đổi hợp đồng `Object.equals(Object)`. Muốn các Collection nhận diện equality theo dữ liệu, hãy ghi đè `equals(Object)` và `hashCode()` đúng quy tắc.

**Ghi nhớ:** Override phụ thuộc vào chữ ký của phương thức được thừa kế; `equals(MyType)` có tham số khác `equals(Object)` nên thường là overload. Mã gọi Java và các Collection dựa vào hợp đồng `equals(Object)`, vì vậy implementation cần ghi đè đúng phương thức ấy.