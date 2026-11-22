# Đối tượng bất biến và lợi ích khi chia sẻ tham chiếu trong Java

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Định nghĩa **immutable object**: đối tượng có trạng thái quan sát được không thay đổi sau khi xây dựng hợp lệ.
- Phân biệt bất biến với biến `final`, field `private`, class không có setter, *read-only view* và collection snapshot.
- Giải thích **aliasing**: nhiều biến, fields và threads giữ reference tới cùng object; hiểu vì sao chia sẻ mutable object cần cẩn trọng còn chia sẻ immutable value object thường dễ suy luận hơn.
- Thiết kế final immutable class/record Java 17+ với constructor validation, private final state, accessor và method tạo bản mới (*wither*), không lộ mutable representation.
- Nhận biết sự khác biệt giữa **shallow immutability** và **deep immutability**, copy mảng, shallow-copy object graph, mutable elements, collections có live backing.
- Sử dụng đúng `String`, `BigInteger`, `BigDecimal`, `LocalDate`, records, `List.of`, `List.copyOf`, `Collections.unmodifiableList` và `Arrays.asList`.
- Phân biệt **sửa object** và **thay giá trị tham chiếu**; hiểu tạo giá trị mới không biến object cũ thành giá trị mới.
- Biết lợi ích của immutable value keys trong `HashMap`/`HashSet`, immutable snapshots trong API, builder mutable tạo sản phẩm bất biến, cấu trúc chia sẻ an toàn.
- Giải thích giới hạn: immutable object không tự làm mọi hệ thống thread-safe, không thay safe publication, không đóng file/socket, không bảo đảm code nhanh hơn hay object luôn được intern.
- Chạy các chương trình Java 17+ độc lập với lệnh `javac`/`java` và stdout kiểm tra.

## 1. Bất biến là gì?

Một Java object **bất biến** nếu trạng thái mà clients quan sát thông qua hợp đồng công khai của nó **không thể bị thay đổi sau khi constructor/factory hoàn thành**. Những methods như `plus`, `withCity`, `concat` có thể trả **giá trị mới** nhưng không mutate object gốc.

Ví dụ với `String`:

~~~java
String original = "Java";
String revised = original.concat(" 17");
~~~

`original` vẫn là `"Java"`, `revised` là `"Java 17"`. Điều này khác `StringBuilder.append`, vốn sửa cùng builder object.

Bất biến là một **hợp đồng về object state**, không phải “biến tham chiếu không được gán lại”. Một biến non-final có thể lần lượt trỏ tới nhiều immutable objects.

### 1.1. Những khái niệm không được đánh đồng

| Khái niệm | Bảo đảm chính | Không tự bảo đảm |
| --- | --- | --- |
| `final` reference field | Field không được gán lại sau khởi tạo hợp lệ | State object được trỏ đến không đổi |
| `private` field | Hạn chế truy cập trực tiếp từ code khác | Không thể lộ mutable reference qua getter |
| Không có setter | Không có setter trong API này | Mutable nested objects/aliases không sửa được |
| Immutable object | Trạng thái quan sát được không đổi sau construction | Không có mutable services bên ngoài hoặc resource lifecycle |
| Unmodifiable view | Caller không mutate qua view | Backing collection không bị nơi khác mutate |
| Unmodifiable snapshot | Cấu trúc snapshot ổn định | Elements không chứa mutable references |
| Record | Components là fields final, có generated methods | Deep copy arrays/lists/custom objects |
| Defensive copy | Copy mức representation mong muốn | Deep copy toàn bộ graph theo một quy tắc tự động |

**Câu hỏi quan trọng:** liệu có **bất kỳ đường tham chiếu hợp lệ nào** cho phép code bên ngoài thay đổi trạng thái mà object công bố sau construction không?

## 2. Aliasing: một object được nhiều nơi tham chiếu

Với Java references:

~~~java
Address shared = new Address("Ha Noi");
Customer a = new Customer("Lan", shared);
Customer b = new Customer("Minh", shared);
~~~

Nếu hai Customers giữ đúng reference tới `shared`, thì cả hai nhìn vào **cùng Address object**. Đây là **aliasing**.

~~~text
Customer A.address --+
                     |
                     v
                  Address
                     ^
                     |
Customer B.address --+
~~~

Nếu Address mutable và ai đó gọi `shared.changeCity("Hue")`, cả hai Customers có thể thấy Hue. Đây là hành vi hợp lệ nhưng có thể gây bugs khi mỗi Customer tưởng mình có bản copy riêng.

### 2.1. Chương trình mutable aliasing

Lưu **`MutableAliasingDemo.java`**:

~~~java
public class MutableAliasingDemo {
    static final class Address {
        private String city;

        Address(String city) {
            this.city = city;
        }

        String city() {
            return city;
        }

        void move(String destination) {
            city = destination;
        }
    }

    static final class Customer {
        private final String name;
        private final Address address;

        Customer(String name, Address address) {
            this.name = name;
            this.address = address;
        }

        String describe() {
            return name + "@" + address.city();
        }
    }

    public static void main(String[] args) {
        Address shared = new Address("Ha Noi");
        Customer lan = new Customer("Lan", shared);
        Customer minh = new Customer("Minh", shared);

        System.out.println("before=" + lan.describe()
                + "," + minh.describe());

        shared.move("Hue");

        System.out.println("after=" + lan.describe()
                + "," + minh.describe());
    }
}
~~~

Chạy:

~~~bash
javac MutableAliasingDemo.java
java MutableAliasingDemo
~~~

Output:

~~~text
before=Lan@Ha Noi,Minh@Ha Noi
after=Lan@Hue,Minh@Hue
~~~

Hai fields `Customer.address` đều `final` nhưng chúng chỉ cố định **reference**, không đóng băng Address object. Khi object được sửa qua `shared`, cả hai Customers đọc cùng trạng thái mới.

### 2.2. Nếu Address bất biến?

Không có `changeCity` và không có mutable representation bị lộ, hai Customers có thể chia sẻ **cùng reference tới Address** mà không sợ người dùng thứ ba sửa chính Address đó.

Khi muốn địa chỉ khác, tạo một Address **mới** rồi tạo/thay reference ở cấp owner thích hợp. Người vẫn giữ reference tới Address cũ có trạng thái cũ.

## 3. Immutable record và việc tạo giá trị mới

Với Java 17:

~~~java
record Address(String city) {
}
~~~

Record này có field component final và component là `String` immutable. Nếu không đưa thêm mutable state/behavior khác, Address có value state ổn định.

Record **không đồng nghĩa** mọi component đều immutable: `record Values(int[] data)` giữ array reference final nhưng array vẫn mutable.

### 3.1. Chương trình chia sẻ record và thay version

Lưu **`ImmutableSharingDemo.java`**:

~~~java
import java.util.Objects;

public class ImmutableSharingDemo {
    record Address(String city) {
        Address {
            Objects.requireNonNull(city, "city");
            if (city.isBlank()) {
                throw new IllegalArgumentException("city required");
            }
        }

        Address withCity(String nextCity) {
            return new Address(nextCity);
        }
    }

    static final class Customer {
        private final String name;
        private final Address address;

        Customer(String name, Address address) {
            this.name = Objects.requireNonNull(name, "name");
            this.address = Objects.requireNonNull(address, "address");
        }

        String describe() {
            return name + "@" + address.city();
        }

        Customer withAddress(Address next) {
            return new Customer(name, next);
        }
    }

    public static void main(String[] args) {
        Address shared = new Address("Ha Noi");
        Customer lan = new Customer("Lan", shared);
        Customer minh = new Customer("Minh", shared);

        System.out.println("same address=" + (shared
                == new Address("Ha Noi")));
        System.out.println("original=" + lan.describe()
                + "," + minh.describe());

        Customer movedLan = lan.withAddress(
                shared.withCity("Hue"));

        System.out.println("old=" + lan.describe());
        System.out.println("new=" + movedLan.describe());
        System.out.println("other=" + minh.describe());
        System.out.println("shared=" + shared.city());
    }
}
~~~

Lệnh:

~~~bash
javac ImmutableSharingDemo.java
java ImmutableSharingDemo
~~~

Output:

~~~text
same address=false
original=Lan@Ha Noi,Minh@Ha Noi
old=Lan@Ha Noi
new=Lan@Hue
other=Minh@Ha Noi
shared=Ha Noi
~~~

**Giải thích:** so `==` ở dòng đầu so identity của hai record instances được tạo riêng nên false. Hai Customers ban đầu cùng sử dụng `shared` nhưng không cần copy Address. `withCity` và `withAddress` tạo values mới; lan và minh cũ vẫn dùng Address Ha Noi.

Điều này giúp code có **snapshot semantics** tự nhiên: giá trị không tự đổi theo thao tác ở nơi khác.

## 4. Bất biến không đồng nghĩa `final`

Phân biệt:

~~~java
final StringBuilder builder = new StringBuilder("A");
builder.append("B"); // Hợp lệ: cùng reference, state thay đổi.
// builder = new StringBuilder("C"); // Không hợp lệ: gán lại final.
~~~

Trong khi:

~~~java
String text = "A";
text = text.concat("B"); // Thay reference sang giá trị String kết quả.
~~~

Biến `text` không final nhưng String objects vẫn immutable.

### 4.1. Chương trình đối chiếu

Lưu **`StringVsBuilderDemo.java`**:

~~~java
public class StringVsBuilderDemo {
    public static void main(String[] args) {
        String first = "Java";
        String alias = first;

        first = first.concat(" 17");

        System.out.println("first=" + first);
        System.out.println("alias=" + alias);
        System.out.println("same reference=" + (first == alias));

        StringBuilder builder = new StringBuilder("Java");
        StringBuilder builderAlias = builder;
        builder.append(" 17");

        System.out.println("builder=" + builder);
        System.out.println("builder alias=" + builderAlias);
        System.out.println("same builder=" + (builder == builderAlias));
    }
}
~~~

Chạy:

~~~bash
javac StringVsBuilderDemo.java
java StringVsBuilderDemo
~~~

Output:

~~~text
first=Java 17
alias=Java
same reference=false
builder=Java 17
builder alias=Java 17
same builder=true
~~~

`concat` không sửa String gốc; `append` sửa StringBuilder mà các aliases cùng thấy. Không suy ra String operations **luôn** cấp phát instance mới nếu kết quả không thay đổi; hợp đồng quan trọng là state gốc không bị mutate.

## 5. Thiết kế immutable class truyền thống

Một class bất biến thường có:

1. State thuộc `private` fields.
2. Fields được gán một lần (`final`) trong constructor hợp lệ.
3. Constructor kiểm tra invariants và không cho `this` escape trước khi hoàn tất.
4. Không có API mutate state.
5. Nếu giữ reference tới mutable object thì copy input/output thích hợp.
6. `final class` hoặc chiến lược kiểm soát subclassing để bảo vệ hợp đồng.
7. `equals`/`hashCode` đúng nếu muốn value equality.

~~~java
public final class Category {
    private final String code;
    private final String displayName;

    public Category(String code, String displayName) {
        this.code = java.util.Objects.requireNonNull(code, "code");
        this.displayName = java.util.Objects.requireNonNull(
                displayName, "displayName");
        if (code.isBlank()) {
            throw new IllegalArgumentException("blank code");
        }
    }

    public String code() {
        return code;
    }

    public String displayName() {
        return displayName;
    }
}
~~~

Đây là class Java 17 hoàn chỉnh (lưu trong file `Category.java`). `String` components immutable, không có setter, class final ngăn subclass phá đặc điểm bất biến thông qua override/extensions.

### 5.1. Bất biến không bắt buộc luôn `final class`

Có thể thiết kế hierarchy bất biến bằng constructor/contracts nghiêm ngặt, nhưng khó bảo đảm hơn. Với value object đơn giản, `final` là lựa chọn dễ hiểu và dễ giữ bất biến.

### 5.2. Bất biến không tự định nghĩa equality

Class trên không override `equals`; theo Object, hai Category instances riêng có thể không equal dù fields giống nhau. Nếu đó là value object, nên override cả `equals`/`hashCode` nhất quán hoặc chọn record phù hợp.

### 5.3. Không publish `this` từ constructor

Đăng ký `this` vào static registry, chạy thread mới giữ `this` hoặc gọi callback bên ngoài trong constructor có thể khiến code khác quan sát object **trước khi initialization hoàn tất**. Việc này cũng ảnh hưởng tới bảo đảm của final field semantics.

Đừng coi `final` là giấy phép tự công bố một object đang xây dở.

## 6. Immutable value object có logic nghiệp vụ

Lưu **`ImmutableMoneyDemo.java`**:

~~~java
import java.util.Locale;
import java.util.Objects;

public class ImmutableMoneyDemo {
    record Money(long cents, String currency) {
        Money {
            Objects.requireNonNull(currency, "currency");
            currency = currency.toUpperCase(Locale.ROOT);
            if (currency.isBlank()) {
                throw new IllegalArgumentException("empty currency");
            }
        }

        Money plus(Money other) {
            Objects.requireNonNull(other, "other");
            if (!currency.equals(other.currency)) {
                throw new IllegalArgumentException("currency mismatch");
            }
            return new Money(Math.addExact(cents, other.cents), currency);
        }

        Money withCents(long updated) {
            return new Money(updated, currency);
        }
    }

    public static void main(String[] args) {
        Money base = new Money(1500, "usd");
        Money fee = new Money(250, "USD");
        Money total = base.plus(fee);

        System.out.println("base=" + base);
        System.out.println("fee=" + fee);
        System.out.println("total=" + total);

        Money revised = total.withCents(2000);
        System.out.println("old total=" + total.cents());
        System.out.println("new total=" + revised.cents());
    }
}
~~~

Chạy:

~~~bash
javac ImmutableMoneyDemo.java
java ImmutableMoneyDemo
~~~

Output:

~~~text
base=Money[cents=1500, currency=USD]
fee=Money[cents=250, currency=USD]
total=Money[cents=1750, currency=USD]
old total=1750
new total=2000
~~~

Cả `plus` và `withCents` trả instance mới, không sửa Money gốc. `Math.addExact` bắt overflow số nguyên. Chuẩn hóa currency uppercase là **quy tắc minh họa**, chưa đủ kiểm tra tiền tệ thực tế (ISO code, minor units, scale/rounding riêng).

Bất biến giúp giảm nguy cơ “tổng tiền đột nhiên đổi” qua alias, nhưng không thay transaction/concurrency control nếu tài khoản hoặc đơn hàng có state mutable tại tầng khác.

## 7. Shallow và deep immutability

Một object có thể có `private final List<Line> lines` mà vẫn **không immutable** nếu:

- `lines` là mutable list được truyền nguyên reference.
- Getter trả đúng list để caller `clear()`.
- List đã unmodifiable nhưng phần tử `Line` có setter, đang được người khác giữ reference.
- Một nested array trong Line vẫn mutable và bị lộ.

### 7.1. Sơ đồ shallow aliasing

~~~text
Immutable-looking Order
    final lines -------------> list structure (unmodifiable)
                                   |
                                   v
                              Mutable Line
                                   ^
                                   |
                            external reference
~~~

List structure không đổi, nhưng `Line.price` có thể thay. Order trả `total()` có thể thay theo thời gian, tức trạng thái quan sát được của Order **chưa thật sự bất biến**.

### 7.2. Copy một tầng không mặc nhiên copy sâu

`new ArrayList<>(source)` tạo list mới nhưng giữ references tới phần tử cũ.

`array.clone()` tạo array object mới nhưng nếu array chứa references tới mutable objects, elements có thể vẫn được chia sẻ. Với `int[]`, clone đã copy primitive values, thường đủ để bảo vệ contents array.

“Deep copy” là quyết định theo **object graph/domain**: cần copy mutable subobjects đến mức loại bỏ aliases nguy hiểm, không nhất thiết copy immutable Strings/records.

Với cycles A↔B và shared subobjects, deep copy tùy tiện có thể làm sai identity graph. Không có toán tử Java duy nhất làm deep-copy phù hợp mọi trường hợp.

## 8. Chia sẻ bất biến an toàn khi field trỏ tới mảng

Mảng `int[]` là mutable. Nếu một object muốn công bố **giá trị bất biến để nhiều references cùng đọc**, chỉ `private final int[]` không đủ: `final` cố định field reference, không đóng băng các phần tử.

Ví dụ một lớp `Digits` có thể giữ snapshot:

~~~java
final class Digits {
    private final int[] values;

    Digits(int[] input) {
        if (input == null) {
            throw new IllegalArgumentException("input");
        }
        this.values = input.clone();
    }

    int at(int index) {
        return values[index];
    }

    int[] copyValues() {
        return values.clone();
    }
}
~~~

Đây là **khai báo lớp**, chưa có `main`. Input clone giúp ngăn thay đổi qua tham chiếu `input`; output clone ngăn caller sửa lại mảng nội bộ thông qua giá trị trả về. Để quan sát đầu vào → sửa alias → kết quả và tự kiểm chứng, có thể viết một `main` lưu `Digits d = new Digits(new int[]{1,2});` rồi kiểm tra `d.at(0)` không đổi sau khi sửa array nguồn hoặc clone trả về.

**Ranh giới bài này:** điều quan trọng là *aliasing + immutable object giúp dễ chia sẻ cùng giá trị*. Bài **“Sao chép phòng vệ đầu vào và đầu ra có thể thay đổi”** hướng dẫn đầy đủ copy các mutable types; bài **“Kiểm tra tính bất biến khi lớp chứa mảng hoặc tập hợp”** đưa test harness chống rò qua cả hai chiều. Với `MutableElement[]` hoặc mảng lồng nhau, `clone()` ngoài cùng chỉ là **shallow copy**.

## 9. Record không tự tạo deep immutability

`record Sample(int[] values)` có field reference final nhưng không tự clone `int[]` khi nhận hay trả; generated `equals` dùng array identity semantics cho component mảng, không tự so nội dung.

### 9.1. Ví dụ record với mảng mutable

Lưu **`ShallowRecordDemo.java`**:

~~~java
public class ShallowRecordDemo {
    record Sample(int[] values) {
    }

    public static void main(String[] args) {
        int[] source = {1, 2};
        Sample a = new Sample(source);
        Sample b = new Sample(new int[] {1, 2});

        System.out.println("record equal=" + a.equals(b));
        System.out.println("before=" + a.values()[0]);

        source[0] = 9;
        System.out.println("input changed=" + a.values()[0]);

        a.values()[1] = 8;
        System.out.println("getter changed=" + source[1]);
    }
}
~~~

Chạy:

~~~bash
javac ShallowRecordDemo.java
java ShallowRecordDemo
~~~

Output:

~~~text
record equal=false
before=1
input changed=9
getter changed=8
~~~

Muốn dùng record với mảng làm value object, cần compact constructor sao chép input, accessor defensive-copy, đồng thời có thể override `equals`/`hashCode` để so array contents nếu domain đòi.

**Không đồng nghĩa mọi record không bất biến**: record chỉ chứa primitive/String/LocalDate hay immutable components khác thường là value object bất biến dễ dùng.

## 10. List snapshot: `List.copyOf` và các giới hạn

`List.copyOf(source)` trả **unmodifiable snapshot về cấu trúc**. Nếu thêm/xóa phần tử ở source sau đó, cấu trúc snapshot không đổi. Nó không copy sâu mutable elements.

### 10.1. Record với list String

Lưu **`RecordListSnapshotDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class RecordListSnapshotDemo {
    record Group(String name, List<String> members) {
        Group {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("name required");
            }
            members = List.copyOf(members);
        }
    }

    public static void main(String[] args) {
        List<String> draft = new ArrayList<>(List.of("Lan"));
        Group group = new Group("A", draft);

        draft.add("Minh");

        System.out.println("draft=" + draft);
        System.out.println("group=" + group.members());

        try {
            group.members().add("Hoa");
        } catch (UnsupportedOperationException expected) {
            System.out.println("group cannot add");
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac RecordListSnapshotDemo.java
java RecordListSnapshotDemo
~~~

Output:

~~~text
draft=[Lan, Minh]
group=[Lan]
group cannot add
~~~

Compact constructor `members = List.copyOf(members)` gán lại parameter để record component lưu snapshot. Các `String` elements là immutable; vì thế cả cấu trúc và nội dung của mỗi element text đều ổn định.

### 10.2. `List.copyOf` không bảo đảm cấp phát list mới

API cho phép tái sử dụng unmodifiable list phù hợp. Không nên dùng `list1 != List.copyOf(list1)` như test hợp đồng. Hãy kiểm tra **giá trị, tính unmodifiable và snapshot semantics**.

`List.copyOf` cũng không chấp nhận null elements; nếu domain cần null làm marker, phải chọn representation khác, thay vì đoán Collections API sẽ giữ null.

## 11. Live unmodifiable view khác snapshot

~~~java
List<String> view =
        java.util.Collections.unmodifiableList(source);
List<String> snapshot = List.copyOf(source);
~~~

Nếu source là mutable list, `view` vẫn có thể phản ánh những thay đổi của backing source. Trong khi đó snapshot không đổi cấu trúc khi source thay sau thời điểm copy.

### 11.1. Demo phân biệt

Lưu **`ViewVsSnapshotDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class ViewVsSnapshotDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>(List.of("A"));
        List<String> view = Collections.unmodifiableList(source);
        List<String> snapshot = List.copyOf(source);

        source.add("B");

        System.out.println("source=" + source);
        System.out.println("view=" + view);
        System.out.println("snapshot=" + snapshot);

        try {
            view.clear();
        } catch (UnsupportedOperationException expected) {
            System.out.println("view cannot clear");
        }

        try {
            snapshot.add("C");
        } catch (UnsupportedOperationException expected) {
            System.out.println("snapshot cannot add");
        }
    }
}
~~~

Chạy:

~~~bash
javac ViewVsSnapshotDemo.java
java ViewVsSnapshotDemo
~~~

Output:

~~~text
source=[A, B]
view=[A, B]
snapshot=[A]
view cannot clear
snapshot cannot add
~~~

Bảo vệ chống sửa qua **một reference** không giống bảo vệ khỏi mutation qua **mọi alias**. Nếu API công bố immutable snapshot, dùng snapshot chứ không chỉ unmodifiable live view.

## 12. List chứa mutable elements vẫn có lỗ hổng

### 12.1. Chương trình phản ví dụ

Lưu **`MutableElementDemo.java`**:

~~~java
import java.util.List;

public class MutableElementDemo {
    static final class Item {
        private String name;

        Item(String name) {
            this.name = name;
        }

        String name() {
            return name;
        }

        void rename(String name) {
            this.name = name;
        }
    }

    static final class Catalog {
        private final List<Item> items;

        Catalog(List<Item> source) {
            items = List.copyOf(source);
        }

        String firstName() {
            return items.get(0).name();
        }
    }

    public static void main(String[] args) {
        Item item = new Item("old");
        Catalog catalog = new Catalog(List.of(item));

        System.out.println("before=" + catalog.firstName());
        item.rename("new");
        System.out.println("after=" + catalog.firstName());
    }
}
~~~

Chạy:

~~~bash
javac MutableElementDemo.java
java MutableElementDemo
~~~

Output:

~~~text
before=old
after=new
~~~

`Catalog.items` final, list unmodifiable nhưng mutable Item object còn được chia sẻ. Vì thế `Catalog` chưa thật sự bất biến về kết quả `firstName()`.

Giải pháp: dùng immutable item record/value object hoặc sao chép mutable Item thành immutable snapshot representation trong constructor, không lộ mutable elements.

## 13. `Arrays.asList` là fixed-size backing view, không immutable

`Arrays.asList(array)` trả list kích thước cố định **backed by array**. `add/remove` không hợp lệ nhưng `set` có thể thay phần tử và phản ánh lên array nguồn.

### 13.1. Ví dụ

Lưu **`ArrayBackedListDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.List;

public class ArrayBackedListDemo {
    public static void main(String[] args) {
        String[] array = {"A", "B"};
        List<String> view = Arrays.asList(array);
        List<String> snapshot = List.copyOf(view);

        array[0] = "X";
        System.out.println("view=" + view);
        System.out.println("snapshot=" + snapshot);

        view.set(1, "Y");
        System.out.println("array=" + Arrays.toString(array));

        try {
            view.add("C");
        } catch (UnsupportedOperationException expected) {
            System.out.println("cannot add");
        }
    }
}
~~~

Chạy:

~~~bash
javac ArrayBackedListDemo.java
java ArrayBackedListDemo
~~~

Output:

~~~text
view=[X, B]
snapshot=[A, B]
array=[X, Y]
cannot add
~~~

**Không dùng fixed-size như từ đồng nghĩa immutable.** Phải phân biệt khả năng thay **số lượng phần tử** với khả năng thay **giá trị phần tử**.

## 14. Immutable aggregate có nhiều values

Một `Order` cần nhiều `OrderLine` có thể giữ unmodifiable snapshot của **immutable line values**, và method cập nhật trả Order object mới.

### 14.1. Chương trình one-to-many

Lưu **`ImmutableOrderDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class ImmutableOrderDemo {
    record Line(String sku, int quantity, long price) {
        Line {
            Objects.requireNonNull(sku, "sku");
            if (sku.isBlank() || quantity <= 0 || price < 0) {
                throw new IllegalArgumentException("invalid line");
            }
        }

        long amount() {
            return Math.multiplyExact((long) quantity, price);
        }
    }

    static final class Order {
        private final String id;
        private final List<Line> lines;

        Order(String id, List<Line> source) {
            this.id = Objects.requireNonNull(id, "id");
            lines = List.copyOf(source);
        }

        int lineCount() {
            return lines.size();
        }

        long total() {
            long total = 0;
            for (Line line : lines) {
                total = Math.addExact(total, line.amount());
            }
            return total;
        }

        Order add(Line line) {
            List<Line> copy = new ArrayList<>(lines);
            copy.add(Objects.requireNonNull(line, "line"));
            return new Order(id, copy);
        }
    }

    public static void main(String[] args) {
        List<Line> draft = new ArrayList<>();
        draft.add(new Line("PEN", 2, 10));

        Order first = new Order("O-1", draft);
        draft.clear();

        Order second = first.add(new Line("BOOK", 1, 50));

        System.out.println("draft=" + draft.size());
        System.out.println("first lines=" + first.lineCount());
        System.out.println("first total=" + first.total());
        System.out.println("second lines=" + second.lineCount());
        System.out.println("second total=" + second.total());
    }
}
~~~

Chạy:

~~~bash
javac ImmutableOrderDemo.java
java ImmutableOrderDemo
~~~

Output:

~~~text
draft=0
first lines=1
first total=20
second lines=2
second total=70
~~~

- `Line` là immutable value (String/primitives).
- `Order` chụp list structure bằng `List.copyOf`.
- Caller sửa `draft` không đổi Order.
- `add` tạo một Order mới, giữ object cũ còn nguyên.
- References tới immutable lines có thể được **chia sẻ** giữa versions mà không cần deep copy.
- Đây là mô hình value snapshot; domain entity Order thực tế có lifecycle/transaction semantics riêng.

## 15. Builder mutable nhưng sản phẩm bất biến

Một builder có thể mutate để dễ thêm/cấu hình dữ liệu. Sản phẩm từ `build()` vẫn bất biến nếu builder không lộ aliases tới internal mutable state.

### 15.1. Demo builder tái sử dụng

Lưu **`BuilderSnapshotDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class BuilderSnapshotDemo {
    record Settings(List<String> features) {
        Settings {
            features = List.copyOf(features);
        }
    }

    static final class Builder {
        private final List<String> features = new ArrayList<>();

        Builder add(String value) {
            features.add(value);
            return this;
        }

        Settings build() {
            return new Settings(features);
        }
    }

    public static void main(String[] args) {
        Builder builder = new Builder().add("search");
        Settings first = builder.build();

        builder.add("report");
        Settings second = builder.build();

        System.out.println("first=" + first.features());
        System.out.println("second=" + second.features());
    }
}
~~~

Chạy:

~~~bash
javac BuilderSnapshotDemo.java
java BuilderSnapshotDemo
~~~

Output:

~~~text
first=[search]
second=[search, report]
~~~

Builder tiếp tục mutate, nhưng mỗi Settings version là một snapshot cấu trúc đã tách. Nếu elements mutable thì builder phải có copy/ownership policy phù hợp; ở đây elements là immutable String.

## 16. Immutable value key và `HashMap`

`HashMap`/`HashSet` yêu cầu các properties của `equals`/`hashCode` nhất quán. Nếu một key đổi state tham gia hash/equality sau khi được đưa vào hash table, lookup có thể thất bại vì vị trí entry đã được tính theo hash cũ.

Immutable keys có state ổn định và dễ tuân thủ hợp đồng. Nhưng **bất biến không đảm bảo hash duy nhất**; collisions vẫn hợp lệ.

### 16.1. Demo key không bị đổi

Lưu **`ImmutableKeyDemo.java`**:

~~~java
import java.util.HashMap;
import java.util.Map;

public class ImmutableKeyDemo {
    record Key(String sku, int version) {
        Key nextVersion() {
            return new Key(sku, version + 1);
        }
    }

    public static void main(String[] args) {
        Map<Key, String> map = new HashMap<>();
        Key first = new Key("PEN", 1);
        map.put(first, "blue");

        Key another = new Key("PEN", 1);
        Key updated = first.nextVersion();

        System.out.println("same value=" + first.equals(another));
        System.out.println("lookup=" + map.get(another));
        System.out.println("first version=" + first.version());
        System.out.println("updated version=" + updated.version());
        System.out.println("updated lookup=" + map.get(updated));
        System.out.println("old lookup=" + map.get(first));
    }
}
~~~

Chạy:

~~~bash
javac ImmutableKeyDemo.java
java ImmutableKeyDemo
~~~

Output:

~~~text
same value=true
lookup=blue
first version=1
updated version=2
updated lookup=null
old lookup=blue
~~~

Key phiên bản 1 đã đưa vào map không hề mutate. `nextVersion` trả key mới. Với key immutable, callers có thể chia sẻ reference hoặc tạo equal key để tra cứu ổn định.

## 17. Nhiều threads đọc cùng immutable snapshot

Nếu object graph **thật sự immutable** và được khởi tạo/công bố đúng, không có race giữa các readers **chỉ đọc** state đó. Điều này thường loại bỏ nhu cầu lock riêng chỉ để bảo vệ dữ liệu bên trong snapshot.

Tuy nhiên:

- **Immutability** không thay **safe publication**, Java Memory Model hay synchronization của các biến holder được update.
- `final` field semantics có những bảo đảm đặc biệt cho correctly constructed objects, với điều kiện không làm `this` escape trong constructor.
- Một service/buffer/connection mutable được object gọi từ methods vẫn có concurrency contract riêng.
- Một mutable `currentSnapshot` holder được update giữa threads cần `volatile`/synchronization/atomic publication phù hợp.
- Nếu two-step business operation cần atomicity, immutable input không tự biến toàn bộ operation thành atomic transaction.

### 17.1. Demo đọc từ hai tasks có output xác định

Lưu **`ImmutableConcurrentReadDemo.java`**:

~~~java
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class ImmutableConcurrentReadDemo {
    record Snapshot(List<Integer> numbers) {
        Snapshot {
            numbers = List.copyOf(numbers);
        }

        int sum() {
            int total = 0;
            for (int value : numbers) {
                total = Math.addExact(total, value);
            }
            return total;
        }
    }

    public static void main(String[] args) throws Exception {
        Snapshot shared = new Snapshot(List.of(1, 2, 3));

        ExecutorService executor = Executors.newFixedThreadPool(2);
        try {
            Future<Integer> a = executor.submit(shared::sum);
            Future<Integer> b = executor.submit(shared::sum);

            System.out.println("first=" + a.get());
            System.out.println("second=" + b.get());
            System.out.println("main=" + shared.sum());
        } finally {
            executor.shutdown();
        }
    }
}
~~~

Chạy:

~~~bash
javac ImmutableConcurrentReadDemo.java
java ImmutableConcurrentReadDemo
~~~

Output:

~~~text
first=6
second=6
main=6
~~~

`Snapshot` chỉ giữ unmodifiable list với immutable Integer values. Hai tasks chỉ đọc. `Future.get()` bảo đảm main chờ kết quả trước khi in theo thứ tự xác định. Executor được shutdown trong finally.

**Không cần đoán thứ tự threads thực thi** để suy luận stdout; chúng không in trực tiếp, và main in theo thứ tự đã viết.

## 18. Safe publication và trạng thái thay version

Một ứng dụng có thể cần **thay reference tới immutable snapshot**:

~~~java
private volatile Snapshot current;
~~~

Writer xây Snapshot mới rồi gán `current = next`. Reader lấy một lần `Snapshot snapshot = current` rồi đọc nhiều fields từ **cùng snapshot**, tránh trạng thái nửa mới nửa cũ khi lần lượt đọc holder nhiều lần.

Nhưng đây chỉ là mẫu minh họa; còn cần:

- Định nghĩa Snapshot được xây và validate trước khi publish.
- Dùng đúng `volatile`/locks/atomic reference tùy requirements.
- Xử lý lost updates nếu nhiều writers dùng read-modify-write.
- Không để mutable components được chia sẻ qua aliases.
- Phân biệt snapshot immutable với **eventual freshness**: reader có thể đã lấy phiên bản cũ hợp lệ trong lúc writer publish phiên bản mới.

Immutable object giúp **mỗi phiên bản** nhất quán; nó không bảo đảm hệ thống luôn đọc phiên bản mới nhất nếu chưa có happens-before phù hợp.

## 19. Những kiểu Java sẵn có hỗ trợ bất biến

| Kiểu/API | Điều đáng ghi nhớ |
| --- | --- |
| `String` | Immutable text; `replace`, `concat` trả kết quả, không sửa gốc |
| `BigInteger` | Immutable số nguyên lớn |
| `BigDecimal` | Immutable thập phân; `equals` phân biệt scale |
| `LocalDate`, `Instant` | Immutable value types từ `java.time` |
| `UUID` | Immutable identifier value |
| Primitive wrappers | Immutable values, nhưng `==` giữa references không thay cho equality nội dung |
| Java records | Component fields final, không deep-copy mutable arrays/lists |
| `List.of`/`Map.of`/`Set.of` | Unmodifiable structures; mutable elements/values vẫn có thể tồn tại |
| `List.copyOf`/`Map.copyOf` | Unmodifiable snapshot cấu trúc; không deep-copy values |
| `Collections.unmodifiableList` | Unmodifiable *view*, backing list có thể thay |
| `Arrays.asList` | Fixed-size list backed by array, `set` hợp lệ |

Một class được mô tả immutable trong API là đối tượng tốt để chia sẻ reference; nhưng hãy kiểm tra **cách dữ liệu được bao lại**. Một `List<Date>` chứa mutable Date objects không trở thành deep immutable chỉ nhờ `List.copyOf`.

## 20. Lợi ích trong thực tế

### 20.1. Giảm mutation gây bất ngờ

Khi gọi `service.process(command)` với immutable command object, service không thể đổi chính object command qua API hợp lệ; caller biết input vẫn giữ giá trị cũ sau lời gọi. Điều này đơn giản hóa debugging và tests.

### 20.2. Snapshots cho log, event, audit, cache

Một immutable event DTO có thể được chuyển cho nhiều consumers, mỗi nơi đọc đúng payload value đã phát. Nếu dữ liệu là mutable array/list được chia sẻ ngầm, log và consumer có thể thấy nội dung thay đổi sau lúc publish — trái kỳ vọng “snapshot”.

### 20.3. Giảm nhu cầu copy để phòng vệ

Khi một service nhận immutable `Address` hoặc `Money`, nó thường không cần clone object chỉ để bảo vệ khỏi caller sửa. Khi dùng mutable DTO, service có thể phải copy hoặc giữ lock/ownership contract.

### 20.4. Dễ reasoning trong đa luồng

Nhiều readers không cùng ghi state immutable. Nhưng external mutable caches, observers, holder references và transaction state vẫn cần concurrency design thích hợp.

### 20.5. Dễ cache/hash/so sánh

Immutable value object ổn định về `equals`/`hashCode` nếu implementation đúng. Một key mutable có thể phá khả năng tra cứu sau khi state hash thay đổi.

### 20.6. Đổi lại: allocation/copy costs

Bất biến không tự tối ưu mọi workload. Tạo object mới khi update thường xuyên có thể tăng allocations, copy list O(n) và GC pressure. **Persistent data structures** có thể dùng structural sharing hiệu quả; không giả định Java `List.copyOf` tự là persistent list với update O(log n).

Hãy đo bằng profiling nếu hiệu năng là yêu cầu, tránh khẳng định immutable luôn nhanh/chậm hơn mutable.

## 21. Chọn immutable hay mutable theo domain

**Immutable phù hợp** cho:

- Value objects như Money, Coordinates, DateRange.
- Command/event/request snapshots không cần thay sau khi tạo.
- Cache keys, identifiers, map/set elements với equality ổn định.
- Shared configuration versions.
- Dữ liệu được chia sẻ rộng giữa modules/threads.

**Mutable có thể phù hợp** cho:

- Builders trong phạm vi local.
- Buffers, streams, active connections có lifecycle.
- Domain entities cần thay state qua operations có validation/transactions.
- Các thuật toán cập nhật liên tục cấu trúc rất lớn với performance constraints.

Một chiến lược cân bằng là **“mutable while building, immutable when sharing”**: dùng local `ArrayList`/`StringBuilder` để tạo dữ liệu, rồi xuất String/immutable snapshot tới người tiêu thụ.

Không cố biến file/socket/DB connection thành “immutable resource” chỉ vì field chứa handle là final. Vòng đời resources vẫn cần `AutoCloseable`/`try-with-resources` và cleanup xác định.

## 22. Các lỗi thường gặp

| Sai lầm | Cách hiểu đúng |
| --- | --- |
| “Final field ⇒ immutable object.” | Final khóa field assignment, không khóa mutable referent. |
| “Private fields ⇒ không mutate được.” | Getter/constructor có thể lộ mutable aliases. |
| “Không có setter ⇒ immutable.” | Có thể còn nested mutable objects hoặc các methods khác sửa gián tiếp. |
| “Record ⇒ deep immutable.” | Records final theo components nhưng không tự copy arrays/lists. |
| “List.copyOf ⇒ immutable elements.” | Unmodifiable structure nhưng references tới elements vẫn shared. |
| “UnmodifiableList ⇒ snapshot.” | Thường là live view qua backing list. |
| “Arrays.asList không add được ⇒ immutable.” | Fixed-size list nhưng có thể `set`. |
| “Clone array ⇒ deep-copy mọi phần tử.” | Object array clone copy references, không clone each object. |
| “Immutable object phải copy mỗi lần truyền.” | Có thể chia sẻ reference không lo mutation của chính object. |
| “Hai immutable objects equal ⇒ `==` true.” | Value equality khác object identity. |
| “Immutable object không tạo GC pressure.” | Nhiều versions/allocations vẫn có chi phí. |
| “Final fields giải quyết hết data races.” | External state/holder updates/publication có quy tắc riêng. |
| “Immutable snapshot luôn mới nhất.” | Snapshot là phiên bản ở thời điểm tạo/lấy. |
| “HashMap key đổi thì map tự rehash.” | Không; dùng immutable key hoặc update entry có kiểm soát. |
| “Immutability làm file tự close.” | Resource lifecycle độc lập với Java object state. |
| “Builder cũng phải immutable.” | Builder có thể mutable; sản phẩm phải tách alias mutable. |
| “All objects must be immutable.” | Tùy domain/performance/lifecycle, giữ mutation trong phạm vi rõ. |
| “Copy từ mutable object luôn rẻ.” | Copy nested graph lớn có thể tốn kém, không tự giả định. |
| “Immutable == thread-safe cho mọi hệ thống.” | Chỉ xử lý shared state của immutable graph; giao tiếp và phối hợp vẫn cần. |

## 23. Checklist thiết kế/kiểm tra một immutable value class

1. Những fields nào là **state quan sát được**?
2. Có phải tất cả fields khởi tạo đầy đủ trong constructor không?
3. Các validation có thực hiện trên chính dữ liệu sẽ được lưu không?
4. Có mutable array/list/Date/StringBuilder/custom references không?
5. Có copy incoming mutable values trước khi lưu không?
6. Có copy hoặc immutable snapshot outgoing values không?
7. Elements bên trong collection có mutable không?
8. Nếu subclassing được phép, subclass có thể phá immutability không?
9. Có setter/method mutate hoặc method gọi external mutable collaborator gây thay đổi state quan sát được không?
10. Có làm `this` escape trong constructor không?
11. Với nhiều threads, object được published đúng contract không?
12. Holder reference thay version có synchronization/volatile/atomic semantics cần thiết không?
13. `equals`/`hashCode` có ổn định và phù hợp domain không?
14. Dùng làm HashMap key có giữ hash-relevant state bất biến không?
15. Có xử lý aliasing, null, arrays, collections và builder reuse trong tests không?
16. Có resource lifecycle ngoài bộ nhớ không?
17. Chi phí allocation/copy có được đo khi quan trọng không?

## 24. Bài tập và đáp án

**Câu 1.** `final List<String> values` có tự làm list immutable không?  
**Đáp án:** Không. Chỉ ngăn gán lại field/biến tham chiếu.

**Câu 2.** Hai Customers dùng chung immutable Address có sao không?  
**Đáp án:** Có thể an toàn về mutation state của Address vì object ấy không đổi.

**Câu 3.** `String a="A"; String b=a; a=a+"B";` thì b là gì?  
**Đáp án:** `"A"`, vì biến a được gán String value kết quả, String gốc không mutate.

**Câu 4.** Hai biến trỏ cùng StringBuilder, một biến gọi append thì biến còn lại thấy gì?  
**Đáp án:** State mới của cùng builder object.

**Câu 5.** `record Data(int[] values)` đã deep immutable chưa?  
**Đáp án:** Chưa. Array mutable và được chia sẻ qua component reference.

**Câu 6.** Constructor clone int[] nhưng getter trả raw internal int[] có an toàn không?  
**Đáp án:** Không. Getter vẫn lộ mutable representation.

**Câu 7.** Vì sao phải copy ở cả input và output boundary?  
**Đáp án:** Ngăn caller sửa state thông qua reference được giữ từ constructor hoặc nhận từ getter.

**Câu 8.** Clone `Address[]` có sao chép từng Address object không?  
**Đáp án:** Không. Chỉ clone mảng ngoài; elements references vẫn shared.

**Câu 9.** `List.copyOf` với mutable elements có deep immutable không?  
**Đáp án:** Không. Chỉ bảo vệ cấu trúc list snapshot.

**Câu 10.** `Collections.unmodifiableList(source)` sau `source.add(x)` có thấy x không?  
**Đáp án:** Có thể có, vì thường là live view backed by source.

**Câu 11.** `List.copyOf(source)` sau `source.add(x)` có tự thêm x không?  
**Đáp án:** Không, cấu trúc snapshot được giữ ổn định.

**Câu 12.** `Arrays.asList(array)` có cho gọi `set` không?  
**Đáp án:** Có, nó backed by array.

**Câu 13.** Khi muốn Money giá trị khác, có nên mutate record Money cũ không?  
**Đáp án:** Không; trả một Money object mới có values mới.

**Câu 14.** Immutable key giúp gì cho HashMap?  
**Đáp án:** Trạng thái tham gia hash/equality không đổi, lookup ổn định.

**Câu 15.** Hai immutable keys khác values có chắc hash khác nhau không?  
**Đáp án:** Không; hash collisions vẫn có thể xảy ra.

**Câu 16.** Một immutable snapshot có thể được hai threads đọc mà không lock để bảo vệ state bên trong không?  
**Đáp án:** Có nếu graph thật sự immutable và được initialized/published đúng; external state vẫn cần phối hợp.

**Câu 17.** `private final List<MutableItem>` đủ deep immutable không?  
**Đáp án:** Không. MutableItem objects có thể bị sửa qua aliases.

**Câu 18.** Builder mutable có thể trả nhiều immutable Settings snapshots không?  
**Đáp án:** Có, nếu build tách cấu trúc dữ liệu mutable và elements phù hợp.

**Câu 19.** Immutability có đảm bảo objects không bao giờ bị GC không?  
**Đáp án:** Không. Garbage collection xét reachability, độc lập với việc object immutable.

**Câu 20.** Immutable object có thể được tham chiếu bằng biến non-final không?  
**Đáp án:** Có. Biến gán lại không làm object cũ mutate.

**Câu 21.** `final` field semantics có bảo đảm mọi code đa luồng tự thread-safe không?  
**Đáp án:** Không. Có điều kiện correctly constructed và các giới hạn visibility/coordination khác.

**Câu 22.** Khi nào nên giữ mutable state?  
**Đáp án:** Khi domain hoặc hiệu năng cần, nhưng giới hạn ownership và xuất immutable snapshot khi chia sẻ.

**Câu 23.** Immutable object có thể giúp tests như thế nào?  
**Đáp án:** Input values không tự thay do alias, làm assertions và trạng thái bước trước/sau dễ dự đoán.

**Câu 24.** Immutable state có thay database transaction không?  
**Đáp án:** Không. Transaction/atomicity là vấn đề khác.

**Câu 25.** Nếu getter trả một `Map.copyOf` snapshot có values là mutable objects, callers có thể thấy changes không?  
**Đáp án:** Có thể có qua values; map cấu trúc unmodifiable không khiến value objects bất biến.

**Câu 26.** Tạo order mới bằng cách copy list line references có cần deep-copy line records immutable không?  
**Đáp án:** Thường không; immutable elements có thể được chia sẻ an toàn.

**Câu 27.** Khi lớp “immutable” dùng lazy mutable cache không đồng bộ, có cần quan tâm không?  
**Đáp án:** Có. Cache là mutable state nội bộ, cần đảm bảo không làm đổi semantics/vi phạm thread safety và visibility.

**Câu 28.** Tại sao `this` escape trong constructor là rủi ro?  
**Đáp án:** Code khác có thể quan sát object chưa hoàn tất khởi tạo, ảnh hưởng invariants và final-field visibility guarantees.

**Câu 29.** Có phải mọi immutable operations phải trả object mới khác identity không?  
**Đáp án:** Không. API có thể tái sử dụng instance khi kết quả bằng cũ; nghĩa quan trọng là không mutate gốc.

**Câu 30.** Hãy nêu một quy tắc thiết kế đơn giản khi cần chia sẻ data rộng.  
**Đáp án:** Dùng immutable value/snapshot đúng nghĩa, validate trong constructor, defensive-copy mutable boundaries, và công bố reference an toàn.

## 25. Tài liệu tham khảo

- Java Language Specification Java SE 17, [`4.12.4 — final Variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.12.4): final variables.
- Java Language Specification, [`8.3.1.2 — final Fields](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.3.1.2): final fields.
- Java Language Specification, [`17.5 — final Field Semantics](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.5): memory visibility của correctly constructed objects.
- Java Language Specification, [`8.10 — Record Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10): record components/constructor semantics.
- Java Platform API, [`String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): immutable text.
- Java Platform API, [`List.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)): unmodifiable snapshot.
- Java Platform API, [`Collections.unmodifiableList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableList(java.util.List)): view semantics.
- Java Platform API, [`Arrays.asList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html#asList(T...)): fixed-size backed list.
- Java Platform API, [`HashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html): hashing contract.
- Java Platform API, [`BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): immutable decimal.
- Java Platform API, [`LocalDate](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/LocalDate.html): immutable date value.
- Java Platform API, [`ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): concurrent task execution.

## Tổng kết

**Đối tượng bất biến** có state quan sát được không thay đổi sau construction. Vì vậy nhiều nơi có thể **chia sẻ cùng reference** mà không phải lo một nơi mutate chính object ấy qua alias. Lợi ích gồm tránh bugs do shared mutable state, giảm defensive copies không cần thiết, dễ dùng làm value keys/snapshots, dễ kiểm thử và chia sẻ cho nhiều readers.

**Không có từ khóa Java duy nhất khiến cả object graph bất biến.** `final` cố định field reference, `private` hạn chế truy cập, `record` có final component fields, `List.copyOf` bảo vệ collection structure; nhưng mutable arrays, elements và references vẫn có thể làm giá trị bị thay đổi gián tiếp. Muốn bất biến thật sự, kiểm tra constructors, defensive copying ở hai chiều, immutable components, quyền subclassing và methods công khai.

Cuối cùng, **bất biến không tự làm toàn bộ hệ thống thread-safe hoặc tối ưu hiệu năng**. Safe publication, external mutable collaborators, holder updates, transaction/lifecycle và chi phí tạo phiên bản mới vẫn cần thiết kế. Với dữ liệu được chia sẻ rộng, ưu tiên **immutable value objects và snapshots**; với phần cần mutation, giữ quyền sửa trong một phạm vi ownership rõ ràng.
