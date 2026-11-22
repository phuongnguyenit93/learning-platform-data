# Nhược điểm của khởi tạo bằng hai cặp ngoặc nhọn (double-brace initialization) trong Java

**Double-brace initialization** là tên gọi không chính thức của kiểu viết `new ArrayList<String>() {{ add("A"); add("B"); }}`. Nó trông giống một cú pháp đặc biệt để tạo và điền dữ liệu vào collection trong một dòng, nhưng **Java không có cấu trúc ngôn ngữ riêng tên là “double brace initialization”**. Đằng sau đó là hai cơ chế Java có sẵn:

1. Cặp ngoặc nhọn thứ nhất `{ ... }` mở **thân của một lớp vô danh (anonymous class)** kế thừa `ArrayList<String>`.
2. Cặp ngoặc nhọn thứ hai `{ ... }` là **instance initializer block** trong lớp vô danh ấy. Khối này chạy khi một instance được xây dựng.

Vì thế, biểu thức không chỉ tạo một `ArrayList` thông thường: nó còn khai báo một **subclass vô danh** của `ArrayList`, rồi thực hiện các lệnh `add` trong lúc khởi tạo subclass. Đó là nguồn gốc của những đánh đổi về kiểu runtime, vòng đời, tham chiếu tới đối tượng bao ngoài, serialization và độ dễ hiểu.

Bài thuộc **Java core – class-object**, nhóm **Lớp vô danh**. Mục tiêu là hiểu **vì sao cách viết hai cặp ngoặc nhọn thường không được khuyến khích** và biết chọn cách thay thế tương ứng trong Java 17: `List.of`, `Set.of`, `Map.of`, `List.copyOf`, `new ArrayList<>(...)`, `new HashMap<>(...)`, `LinkedHashMap`, hàm tạo riêng hoặc Builder.

Các chương trình độc lập dưới đây dùng Java **17+**, có tên tệp, lệnh biên dịch và stdout xác định. Đoạn mã cố ý lỗi biên dịch được đánh dấu rõ, không coi là ví dụ runnable.

## 1. Nhận diện chính xác hai cặp ngoặc nhọn

Hãy nhìn biểu thức:

~~~java
java.util.List<String> names =
        new java.util.ArrayList<String>() {{
            add("An");
            add("Binh");
        }};
~~~

Đây là **snippet hợp lệ trong một method hoặc initializer thích hợp**, không phải cả một chương trình có `main`.

Phân tích từng thành phần:

~~~text
new ArrayList<String>() {     ← mở class body của subclass vô danh
    {                         ← mở instance initializer block
        add("An");            ← gọi method của object đang khởi tạo
        add("Binh");
    }                         ← đóng instance initializer
};                            ← đóng anonymous class và kết thúc lệnh
~~~

Từ khóa `new` bắt đầu một **class instance creation expression**. Dấu `()` gọi superclass constructor phù hợp (ở đây là constructor không tham số của ArrayList). Lớp vô danh được tạo là một subtype của ArrayList. Sau khi superclass được khởi tạo thích hợp, instance initializer của subtype chạy và thêm phần tử.

**Đừng nhầm** hai cặp ngoặc này với lambda `() -> { ... }`, với array initializer `new String[] { ... }` hoặc với collection literal ở ngôn ngữ khác. Java 17 không có cú pháp literal tổng quát `["An", "Binh"]` để tạo ArrayList.

## 2. Ví dụ runnable 1 — collection chứa đúng dữ liệu nhưng class khác

Tạo tệp **`DoubleBraceBasicsDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class DoubleBraceBasicsDemo {
    public static void main(String[] args) {
        List<String> doubleBrace = new ArrayList<String>() {{
            add("An");
            add("Binh");
        }};

        List<String> ordinary =
                new ArrayList<>(List.of("An", "Binh"));

        System.out.println("doubleBrace=" + doubleBrace);
        System.out.println("ordinary=" + ordinary);
        System.out.println("equal content="
                + doubleBrace.equals(ordinary));
        System.out.println("anonymous="
                + doubleBrace.getClass().isAnonymousClass());
        System.out.println("exact ArrayList="
                + (doubleBrace.getClass() == ArrayList.class));
        System.out.println("ordinary exact ArrayList="
                + (ordinary.getClass() == ArrayList.class));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 DoubleBraceBasicsDemo.java
java DoubleBraceBasicsDemo
~~~

**Stdout chính xác:**

~~~text
doubleBrace=[An, Binh]
ordinary=[An, Binh]
equal content=true
anonymous=true
exact ArrayList=false
ordinary exact ArrayList=true
~~~

Hai collections có **dữ liệu bằng nhau theo `List.equals`**, nhưng runtime class không giống nhau. `doubleBrace` là instance của một **subclass vô danh**, còn `ordinary` là instance của chính `ArrayList`.

Chính vì `List.equals` so nội dung theo thứ tự mà kết quả `equal content=true`; đừng vội suy rộng rằng **mọi** lớp trong Java đều xem subclass và superclass có cùng dữ liệu là bằng nhau.

## 3. Vì sao cách viết này từng hấp dẫn?

Trước khi Java cung cấp các collection factory methods tiện dụng như `List.of`, `Set.of`, `Map.of` (Java 9+), người học thường muốn rút ngắn:

~~~java
List<String> names = new ArrayList<>();
names.add("An");
names.add("Binh");
~~~

thành một biểu thức duy nhất dùng được ở chỗ khởi tạo field hoặc truyền đối số:

~~~java
consume(new ArrayList<String>() {{
    add("An");
    add("Binh");
}});
~~~

Đoạn `consume(...)` là **minh họa**, giả định có method `consume(List<String>)` tương ứng.

Tác dụng nhìn thấy là **tiện viết tại chỗ**. Nhưng lợi ích về vài dòng mã đổi lấy những điều người đọc phải nhận biết: một anonymous subclass mới, một initializer chạy ngay lúc construction, possible outer reference/capture, và một runtime type khác `ArrayList.class`.

Khi hiểu cơ chế thật, bạn sẽ thấy đây **không phải collection literal**, không làm collection immutable, và không bảo đảm serialization đơn giản.

## 4. So sánh đường khởi tạo: superclass constructor → instance initializer

Trong Java, một instance initializer `{ ... }` là các statements thực thi trong quá trình tạo object theo quy tắc initialization của class, sau khi superclass construction diễn ra thích hợp.

Ví dụ kiểu khái niệm:

~~~java
class TraceList extends java.util.ArrayList<String> {
    TraceList() {
        System.out.println("TraceList constructor");
    }
}
~~~

Nếu viết `new TraceList() {{ add("A"); }}`, bạn đang tạo **anonymous subclass của TraceList**, không chỉ tạo TraceList. Trước khi biểu thức trả về object, các lệnh thuộc instance initializer của anonymous subclass được chạy.

Khối initializer có thể có **side effects**: ghi log, sửa một object được capture hoặc ném exception. Vì thế, cách tạo collection tưởng như chỉ “liệt kê dữ liệu” lại có thể thực thi code tùy ý ngay lúc khởi tạo.

## 5. Ví dụ runnable 2 — thứ tự constructor và initializer

Tạo tệp **`DoubleBraceOrderDemo.java`**:

~~~java
import java.util.ArrayList;

class TraceList extends ArrayList<String> {
    TraceList() {
        System.out.println("TraceList constructor");
    }
}

public class DoubleBraceOrderDemo {
    public static void main(String[] args) {
        System.out.println("before new");

        TraceList values = new TraceList() {{
            System.out.println("anonymous initializer");
            add("A");
        }};

        System.out.println("after new");
        System.out.println("values=" + values);
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 DoubleBraceOrderDemo.java
java DoubleBraceOrderDemo
~~~

**Stdout:**

~~~text
before new
TraceList constructor
anonymous initializer
after new
values=[A]
~~~

Constructor của `TraceList` chạy trước phần instance initializer của anonymous subclass. Sau khi initializer hoàn tất và biểu thức `new` trả về, chương trình mới in `after new`.

**Đừng nhầm thời điểm:** những lời gọi `add` trong initializer **không chờ** tới lúc bạn sử dụng list. Chúng diễn ra ngay trong quá trình creation.

## 6. Nhược điểm 1 — sinh ra một anonymous subclass không cần thiết

Một danh sách dữ liệu thông thường thường không cần một subclass. Nhưng mỗi biểu thức double-brace là một **anonymous class declaration**:

~~~java
List<String> first = new ArrayList<String>() {{
    add("A");
}};

List<String> second = new ArrayList<String>() {{
    add("B");
}};
~~~

Đây là các snippets trong method. Hai biểu thức xuất hiện ở **hai vị trí source khác nhau**, nên khai báo **hai anonymous classes khác nhau**; mỗi biểu thức còn tạo object riêng khi được đánh giá.

Điều này có thể làm việc debug và phản chiếu kiểu khó hiểu:

- `getClass()` không trả `ArrayList.class`, dù object vẫn là một `ArrayList` theo `instanceof`.
- Stack traces và debugger có thể thể hiện tên compiler-generated.
- Framework dùng runtime class chính xác có thể xử lý một anonymous subtype khác với base class.
- Mỗi anonymous class declaration có metadata/class initialization riêng, dù mức ảnh hưởng cụ thể phụ thuộc compiler, runtime và số lượng declarations.

**Không thổi phồng:** một biểu thức double-brace nằm trong một loop không nhất thiết tạo **một class mới cho mỗi iteration**. Nó tạo **một object mới mỗi lần `new` chạy**, nhưng các objects từ **cùng declaration** thường có cùng runtime class. Đây là điểm phân biệt class identity và object identity.

## 7. Ví dụ runnable 3 — một declaration, nhiều objects

Tạo tệp **`AnonymousClassIdentityDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class AnonymousClassIdentityDemo {
    static List<String> make(String value) {
        return new ArrayList<String>() {{
            add(value);
        }};
    }

    public static void main(String[] args) {
        List<String> a = make("A");
        List<String> b = make("B");

        List<String> anotherDeclaration =
                new ArrayList<String>() {{
                    add("C");
                }};

        System.out.println("a=" + a);
        System.out.println("b=" + b);
        System.out.println("different objects=" + (a != b));
        System.out.println("same class="
                + (a.getClass() == b.getClass()));
        System.out.println("other declaration same class="
                + (a.getClass()
                   == anotherDeclaration.getClass()));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 AnonymousClassIdentityDemo.java
java AnonymousClassIdentityDemo
~~~

**Stdout:**

~~~text
a=[A]
b=[B]
different objects=true
same class=true
other declaration same class=false
~~~

Hai lần gọi `make` tạo instances khác nhau của **cùng anonymous class declaration** trong `make`; captured value riêng là A/B. Biểu thức ở `main` định nghĩa **một anonymous class khác** nên `getClass()==` false.

**Đối chiếu:** `new ArrayList<>(List.of("A"))` tạo chính một ArrayList, không thêm subclass cho mục đích điền vài phần tử.

## 8. Nhược điểm 2 — dễ giữ tham chiếu tới đối tượng bao ngoài

Trong một **instance method** của lớp `Owner`, anonymous inner class được khai báo trong instance context có thể có liên hệ với enclosing instance `Owner.this`. Nếu class body tham chiếu state của `Owner`, nó cần một đường tới object ấy.

~~~java
class Owner {
    private final String name = "O1";

    java.util.List<String> create() {
        return new java.util.ArrayList<String>() {{
            add(Owner.this.name);
        }};
    }
}
~~~

Đây là class minh họa hợp lệ. Trong instance initializer, `Owner.this.name` chỉ tới `Owner` object đã gọi `create()`; `this` của initializer lại là anonymous ArrayList instance.

Nếu collection được đưa vào **cache/listener registry sống lâu**, reference tới enclosing object có thể góp phần giữ object ấy reachable, khiến việc giải phóng tài nguyên hoặc bộ nhớ xảy ra muộn hơn dự định.

**Cách diễn đạt chính xác:** không phải mọi trường hợp double-brace đều tạo một field `this$0` với tên/biểu diễn cố định. Compiler, Java version và nhu cầu thực tế có thể ảnh hưởng bytecode. Rủi ro là **ngữ nghĩa enclosing instance/captured references**, đặc biệt rõ khi body thật sự cần `Owner.this`. Không nên dựa vào tên synthetic field cụ thể để xây logic ứng dụng.

## 9. Ví dụ runnable 4 — `this` là list vô danh, không phải outer

Tạo tệp **`OuterReferenceDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

final class DocumentOwner {
    private final String ownerName;

    DocumentOwner(String ownerName) {
        this.ownerName = ownerName;
    }

    List<String> makeList() {
        return new ArrayList<String>() {{
            add("owner=" + DocumentOwner.this.ownerName);
            add("anonymous=" + getClass().isAnonymousClass());
        }};
    }
}

public class OuterReferenceDemo {
    public static void main(String[] args) {
        DocumentOwner owner = new DocumentOwner("An");
        List<String> values = owner.makeList();

        System.out.println(values);
        System.out.println("is list=" + (values instanceof List));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 OuterReferenceDemo.java
java OuterReferenceDemo
~~~

**Stdout chính xác:**

~~~text
[owner=An, anonymous=true]
is list=true
~~~

Trong initializer của anonymous ArrayList, `getClass()` không có receiver tường minh nên tương đương đọc trên `this` của anonymous object; `DocumentOwner.this.ownerName` lại đọc outer object.

Nếu chỉ cần lưu chuỗi `"An"`, dùng một value được tính trước và một ArrayList bình thường thường **ít ràng buộc lifetime** hơn giữ cơ chế anonymous subclass cần enclosing owner.

## 10. Không phải cứ dùng double-brace là có outer instance

Double-brace được viết trong **static method** không có enclosing instance của class chứa method để dùng `Outer.this`. Nó vẫn tạo anonymous subclass và chạy instance initializer.

~~~java
class Lists {
    static java.util.List<String> values() {
        return new java.util.ArrayList<String>() {{
            add("A");
        }};
    }
}
~~~

Đây là class minh họa hợp lệ. Code này không cần một `Lists` object. Nó vẫn mang các đánh đổi khác: subclass vô danh, khởi tạo qua block, runtime type khác ArrayList và có thể capture local variables/parameters của static method.

Vì vậy câu “double-brace **luôn** leak outer instance” là quá mức. Nên nói: trong **instance context**, đặc biệt khi body tham chiếu `Outer.this`, có **nguy cơ giữ enclosing object không cần thiết**; trong static context nguy cơ ấy không xuất hiện theo cùng cách.

## 11. Ví dụ runnable 5 — double-brace trong static method

Tạo tệp **`StaticDoubleBraceDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class StaticDoubleBraceDemo {
    static List<String> create() {
        String message = "static";

        return new ArrayList<String>() {{
            add(message);
        }};
    }

    public static void main(String[] args) {
        List<String> values = create();
        System.out.println("values=" + values);
        System.out.println("anonymous="
                + values.getClass().isAnonymousClass());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 StaticDoubleBraceDemo.java
java StaticDoubleBraceDemo
~~~

**Stdout:**

~~~text
values=[static]
anonymous=true
~~~

`message` là local variable effectively final được capture bởi anonymous class. Tuy không có `StaticDoubleBraceDemo.this`, collection vẫn là anonymous subclass. Cách viết không trở thành “collection literal” chỉ vì xuất hiện trong static context.

## 12. Nhược điểm 3 — có thể làm serialization thất bại

`ArrayList` triển khai `Serializable`. Vì subclass vô danh thừa hưởng điều đó, bạn có thể thấy:

~~~java
values instanceof java.io.Serializable
~~~

trả true, rồi tưởng chắc chắn ghi được object qua `ObjectOutputStream`.

Nhưng serialization phải xử lý **toàn bộ phần state được serialize** của object. Anonymous subclass có thể giữ **captured data** hoặc **reference tới outer object không serializable**; các references ấy làm serialization thất bại.

**Không khẳng định** mọi double-brace list đều không serializable. Một anonymous subclass đơn giản không giữ state ngoài có thể được serialize trong điều kiện phù hợp. Rủi ro nằm ở việc thêm **anonymous implementation và captured references** khiến khả năng serialize khó dự đoán hơn một cấu trúc dữ liệu thuần.

Ví dụ tiếp theo cố ý giữ một field tham chiếu Outer không serializable để tạo ra một lỗi **đáng tin, có thể tái hiện**, không phụ thuộc tên synthetic fields.

## 13. Ví dụ runnable 6 — `Serializable` nhưng serialization vẫn lỗi

Tạo tệp **`DoubleBraceSerializationDemo.java`**:

~~~java
import java.io.ByteArrayOutputStream;
import java.io.NotSerializableException;
import java.io.ObjectOutputStream;
import java.util.ArrayList;
import java.util.List;

final class NonSerializableOwner {
    private final String label = "owner";

    List<String> createList() {
        return new ArrayList<String>() {
            private final NonSerializableOwner capturedOwner =
                    NonSerializableOwner.this;

            {
                add("A");
            }
        };
    }
}

public class DoubleBraceSerializationDemo {
    public static void main(String[] args) throws Exception {
        List<String> values =
                new NonSerializableOwner().createList();

        System.out.println("serializable="
                + (values instanceof java.io.Serializable));
        System.out.println("values=" + values);

        try (var bytes = new ByteArrayOutputStream();
             var output = new ObjectOutputStream(bytes)) {
            output.writeObject(values);
            System.out.println("serialization success");
        } catch (NotSerializableException ex) {
            System.out.println("serialization="
                    + ex.getClass().getSimpleName());
        }
    }
}
~~~

Lệnh:

~~~bash
javac -encoding UTF-8 DoubleBraceSerializationDemo.java
java DoubleBraceSerializationDemo
~~~

**Stdout:**

~~~text
serializable=true
values=[A]
serialization=NotSerializableException
~~~

Giải thích: ArrayList implements Serializable, nên phép `instanceof Serializable` trả true. Nhưng anonymous subclass trong ví dụ có field `capturedOwner` trỏ đến `NonSerializableOwner`, một class không triển khai Serializable. Khi serialization đi qua object graph, nó ném `NotSerializableException`.

Đây là minh chứng rằng **“đối tượng thuộc kiểu Serializable” không có nghĩa toàn bộ object graph chắc chắn serialize được**. Đừng giải quyết bằng cách cho mọi service/controller implement Serializable một cách mù quáng: cần thiết kế snapshot data/DTO độc lập với object runtime và lifecycle.

## 14. Nhược điểm 4 — runtime type có thể gây bất ngờ cho code dựa vào class chính xác

Với `ArrayList`, phần lớn API theo interface `List` vẫn hoạt động bình thường. Nhưng nếu ứng dụng hoặc framework kiểm tra:

~~~java
value.getClass() == ArrayList.class
~~~

thì double-brace list không thỏa, dù:

~~~java
value instanceof ArrayList
~~~

vẫn true.

Có hai cấp độ khác biệt:

- **Subtyping:** anonymous subclass **là một** ArrayList theo quy tắc kế thừa; `instanceof ArrayList` true.
- **Exact runtime class:** nó **không phải chính class ArrayList**; `getClass()==ArrayList.class` false.

Một số framework có thể xử lý object theo runtime subtype, annotations hoặc serialization metadata; anonymous subclass có thể trở thành kiểu không mong đợi. Không nên khẳng định mọi framework đều lỗi: **phải kiểm tra contract của framework đang sử dụng**.

Với code thông thường, hãy ưu tiên lập trình dựa trên `List`/ `Map` interfaces thay vì yêu cầu exact implementation class nếu không thực sự cần.

## 15. Vấn đề với `equals` của các class nhạy cảm với runtime type

Một lớp tự định nghĩa có thể triển khai `equals` theo chính xác runtime class. Khi đó anonymous subclass từ double-brace có thể làm **hai objects có cùng dữ liệu nhưng không equal**.

Ví dụ:

~~~java
class StrictList extends java.util.ArrayList<String> {
    @Override
    public boolean equals(Object other) {
        return other != null
                && other.getClass() == getClass()
                && super.equals(other);
    }

    @Override
    public int hashCode() {
        return super.hashCode();
    }
}
~~~

Đây là class minh họa hợp lệ. `StrictList.equals` chủ động yêu cầu **same exact runtime class**, không chỉ so contents. Việc implement equals như vậy là một quyết định cần cân nhắc theo hợp đồng equality; nó được dùng ở đây chỉ để làm rõ rủi ro của anonymous subclass.

Nếu dùng `new StrictList() {{ add("A"); }}`, instance có runtime class là anonymous subclass, nên có thể khác `new StrictList()` dù cùng nội dung.

**Không áp dụng suy luận này cho `ArrayList.equals` mặc định:** ArrayList so các phần tử của List nên hai danh sách có thể equal dù khác runtime class, như ví dụ 1.

## 16. Ví dụ runnable 7 — equality phụ thuộc exact class

Tạo tệp **`ExactClassEqualityDemo.java`**:

~~~java
import java.util.ArrayList;

class StrictList extends ArrayList<String> {
    @Override
    public boolean equals(Object other) {
        return other != null
                && other.getClass() == getClass()
                && super.equals(other);
    }

    @Override
    public int hashCode() {
        return super.hashCode();
    }
}

public class ExactClassEqualityDemo {
    public static void main(String[] args) {
        StrictList ordinary = new StrictList();
        ordinary.add("A");

        StrictList anonymous = new StrictList() {{
            add("A");
        }};

        System.out.println("contents="
                + ordinary.toString().equals(
                    anonymous.toString()));
        System.out.println("ordinary equals anonymous="
                + ordinary.equals(anonymous));
        System.out.println("anonymous equals ordinary="
                + anonymous.equals(ordinary));
        System.out.println("same runtime class="
                + (ordinary.getClass()
                    == anonymous.getClass()));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 ExactClassEqualityDemo.java
java ExactClassEqualityDemo
~~~

**Stdout:**

~~~text
contents=true
ordinary equals anonymous=false
anonymous equals ordinary=false
same runtime class=false
~~~

Hai objects in cùng chuỗi `[A]`, nhưng custom equality của StrictList từ chối objects khác exact runtime class. Ở đây `hashCode` vẫn tuân yêu cầu nếu hai objects bằng nhau thì hash phải bằng; hai objects **không** bằng nhau vẫn được phép có cùng hash.

Ví dụ này nhắc một nguyên tắc: **subclass vô danh là một thay đổi kiểu**, không chỉ một lối viết ngắn để điền dữ liệu.

## 17. Nhược điểm 5 — code dễ làm người đọc nhầm về `this`

Trong instance initializer của anonymous class, `this` chỉ **anonymous object**, không phải enclosing outer object. Nếu từ bên trong initializer gọi `add(...)`, lời gọi ấy tương đương `this.add(...)` với receiver là collection đang tạo.

~~~java
class Container {
    private final String label = "outer";

    java.util.List<String> build() {
        return new java.util.ArrayList<String>() {{
            add("anonymous=" + getClass().isAnonymousClass());
            add("label=" + Container.this.label);
        }};
    }
}
~~~

Đây là class minh họa hợp lệ. Trong `build()`, `Container.this.label` chỉ enclosing instance còn `this.getClass()` chỉ anonymous ArrayList instance.

Việc các biểu thức có dấu `this` khác nghĩa so với method bao ngoài làm double-brace **khó review hơn** khi body phức tạp, nhất là khi có trùng tên field.

Nếu không cần subclassing mà chỉ cần tập hợp dữ liệu, một builder/list bình thường tránh hoàn toàn scope `this` mới không cần thiết.

## 18. Nhược điểm 6 — side effects và exception trong lúc tạo dữ liệu

Người đọc có thể nghĩ rằng:

~~~java
List<String> words = new ArrayList<String>() {{
    add("A");
    add("B");
}};
~~~

là “tạo dữ liệu” tương tự một literal. Thực tế initializer có thể gọi methods bất kỳ, cập nhật đối tượng khác hoặc ném exception. Nếu initializer lỗi, biểu thức `new` **không trả một object hoàn chỉnh cho phép gán**; nhưng **side effects đã xảy ra ở bên ngoài không tự được rollback**.

Đây là lý do nên giữ initialization logic đơn giản và tránh trộn business operations vào một collection initializer ẩn sau cặp ngoặc thứ hai.

Với những thao tác cần validation, tính toán hoặc phát sinh side effects, dùng method factory có tên hoặc một block code bình thường dễ thấy điểm lỗi hơn.

## 19. Ví dụ runnable 8 — tạo thất bại, tác dụng phụ bên ngoài vẫn tồn tại

Tạo tệp **`DoubleBraceFailureDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class DoubleBraceFailureDemo {
    public static void main(String[] args) {
        List<String> audit = new ArrayList<>();

        try {
            List<String> result = new ArrayList<String>() {{
                audit.add("initializer started");
                add("A");

                if (audit.size() == 1) {
                    throw new IllegalArgumentException("blocked");
                }
            }};
            System.out.println("result=" + result);
        } catch (IllegalArgumentException ex) {
            System.out.println("failure=" + ex.getMessage());
        }

        System.out.println("audit=" + audit);
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 DoubleBraceFailureDemo.java
java DoubleBraceFailureDemo
~~~

**Stdout:**

~~~text
failure=blocked
audit=[initializer started]
~~~

Anonymous initializer sửa list `audit` nằm bên ngoài rồi ném exception. Biến `result` không nhận được object vì creation thất bại; tuy vậy phần tử `initializer started` vẫn ở trong audit.

**Không xem đây là lỗi riêng của ArrayList:** bất kỳ constructor/factory/initializer nào có side effects cũng có thể gặp vấn đề tương tự. Double-brace đặc biệt dễ che bớt thực tế rằng bên trong cái trông như “literal dữ liệu” có một **block statements có thể lỗi**.

## 20. Nhược điểm 7 — rủi ro kế thừa và khả năng mở rộng

Double-brace là **anonymous subclassing**. Nó chỉ dùng được khi superclass cho phép subclassing và constructor cần gọi có quyền truy cập phù hợp.

Ví dụ class `String` được khai báo final. Đoạn sau **cố ý không biên dịch**:

~~~java
// String s = new String() {{ /* ... */ }};
~~~

Không có cách viết double-brace tương tự để subclass một **final class**.

Với class có constructor private/không accessible, class sealed có quy tắc permits, hoặc class thiết kế không dành cho kế thừa, anonymous subclassing có thể không hợp lệ hoặc là ý tưởng không tốt.

Ngoài chuyện biên dịch, nếu superclass có protected hooks hoặc overridable methods, một subclass vô danh có thể tham gia vòng đời object bằng cách khác với người đọc mong đợi. **Đừng dùng subclassing chỉ để điền vài phần tử**, nhất là với domain types có invariants và lifecycle phức tạp.

## 21. Nhược điểm 8 — khó quan sát code và debug

Tên runtime của anonymous class thường là một binary name do compiler tạo; ví dụ có thể xuất hiện dấu `$` và chỉ số. Số thứ tự ấy **không phải API ổn định** để lưu trong cấu hình, database hoặc so sánh nghiệp vụ.

Debug stack trace cũng có thể trỏ tới initializer hoặc anonymous class chứ không phải một constructor/factory có tên do ứng dụng đặt. Nếu khối initializer dài, việc lần theo lỗi sẽ kém trực quan hơn một method như `buildRules()` hoặc `createSeedData()`.

**Không khẳng định** JVM luôn tạo cùng một bộ bytecode/synthetic fields giữa mọi compiler. Mấu chốt là source code đã tạo **một subtype vô danh không cần thiết**, làm danh tính triển khai khó nhận diện hơn.

Độ dễ đọc thường là nhược điểm nổi bật nhất ở codebase lớn: một người đọc `Map.of("a",1,"b",2)` hiểu ngay đây là các entries, còn người đọc double-brace phải nhận ra **anonymous subclass + instance initializer** trước khi đánh giá tiếp.

## 22. Nhược điểm 9 — không tự bất biến hoặc thread-safe

Một double-brace ArrayList/HashMap thông thường **vẫn mutable**:

~~~java
List<String> names = new ArrayList<String>() {{
    add("A");
}};
names.add("B");
~~~

Đây là snippet hợp lệ trong method. List sau đó chứa A và B; việc dùng hai cặp ngoặc không khóa dữ liệu.

Ngược lại, `List.of("A")` tạo một **unmodifiable list** (không hỗ trợ các mutation methods). Nhưng không được suy ra mọi phần tử bên trong List.of đều immutable: list vẫn có thể giữ references tới **mutable objects**.

Với concurrency, double-brace không giúp `ArrayList` hoặc `HashMap` tự an toàn khi nhiều threads cùng sửa. Cần synchronization hoặc collection concurrent phù hợp với bài toán.

## 23. Ví dụ runnable 9 — phân biệt mutable list và unmodifiable list

Tạo tệp **`MutableVsUnmodifiableDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class MutableVsUnmodifiableDemo {
    public static void main(String[] args) {
        List<String> concise = List.of("A", "B");
        List<String> editable = new ArrayList<>(concise);

        editable.add("C");

        System.out.println("concise=" + concise);
        System.out.println("editable=" + editable);

        try {
            concise.add("C");
        } catch (UnsupportedOperationException ex) {
            System.out.println("concise mutation="
                    + ex.getClass().getSimpleName());
        }

        System.out.println("editable class="
                + (editable.getClass() == ArrayList.class));
    }
}
~~~

Lệnh:

~~~bash
javac -encoding UTF-8 MutableVsUnmodifiableDemo.java
java MutableVsUnmodifiableDemo
~~~

**Stdout:**

~~~text
concise=[A, B]
editable=[A, B, C]
concise mutation=UnsupportedOperationException
editable class=true
~~~

Cách chọn:

- Nếu cần **dữ liệu cố định không được thêm/xóa**, `List.of` thường dễ đọc.
- Nếu cần **ArrayList mutable**, dùng `new ArrayList<>(List.of(...))`: tạo đúng ArrayList và có dữ liệu khởi tạo.
- Nếu cần **snapshot** của một collection hiện có, `List.copyOf(source)` cung cấp unmodifiable list, nhưng bản thân thao tác ấy không deep-copy mutable elements.

Không dùng `List.of` chỉ vì ngắn, rồi ngạc nhiên khi `add` ném exception; cũng không dùng double-brace chỉ để mong kết quả immutable.

## 24. Cách thay thế 1 — `List.of` và `new ArrayList<>(...)`

Bảng chọn nhanh:

| Mục đích | Cách Java 17 thường dùng |
| --- | --- |
| Danh sách nhỏ, không sửa cấu trúc | `List.of("A", "B")` |
| ArrayList sửa được sau khởi tạo | `new ArrayList<>(List.of("A", "B"))` |
| Empty mutable list | `new ArrayList<String>()` |
| Snapshot không sửa cấu trúc từ collection có sẵn | `List.copyOf(existing)` |
| List từ các phần tử có thể là `null` | `new ArrayList<>(Arrays.asList("A", null))` nếu nghiệp vụ cho phép |
| Dữ liệu tạo nhiều bước/validation | Method factory/builder rõ ràng |

**Đừng nhầm contract:** `List.of` không chấp nhận `null`, cho phép phần tử trùng, giữ thứ tự arguments và trả unmodifiable list. `List.copyOf` không chấp nhận phần tử null trong source. `Arrays.asList` trả một list kích thước cố định được backing bởi array trong cách dùng phù hợp, **không phải ArrayList mutable hỗ trợ add/remove**; bọc nó bằng `new ArrayList<>(...)` nếu cần list thêm/bớt.

Nếu dự kiến cập nhật danh sách liên tục, cách viết mutable ArrayList với constructor có thể rõ ràng hơn việc tạo một unmodifiable list trung gian chỉ để copy; khi dữ liệu phức tạp, viết các lệnh `add` thông thường thường dễ kiểm tra nhất.

## 25. Cách thay thế 2 — `Set.of`, `Map.of`, `Map.ofEntries`

Double-brace thường được thấy với HashSet và HashMap:

~~~java
Set<String> flags = new HashSet<String>() {{
    add("READ");
    add("WRITE");
}};

Map<String, Integer> scores = new HashMap<String, Integer>() {{
    put("An", 10);
    put("Binh", 20);
}};
~~~

Đây là các snippets, giả định imports đầy đủ. Với dữ liệu **không cần mutate cấu trúc**, Java 17 cho:

~~~java
Set<String> flags = Set.of("READ", "WRITE");
Map<String, Integer> scores =
        Map.of("An", 10, "Binh", 20);
~~~

Khi cần nhiều entries, dùng `Map.ofEntries(Map.entry(...), ...)`. Các factory methods này **không phải bản sao chức năng tuyệt đối** của double-brace HashMap/HashSet:

- `Set.of` và `Map.of` tạo **unmodifiable** collections.
- `Set.of` từ chối phần tử trùng; `Map.of` từ chối keys trùng.
- Những factory methods này từ chối `null` theo API.
- **Thứ tự duyệt Set/Map factory không được bảo đảm** như `List.of`; không viết expected stdout phụ thuộc vào `Map.of(...).toString()` hoặc thứ tự iteration.
- `HashMap.put` với cùng key **thay giá trị trước**, trong khi Map.of ném IllegalArgumentException cho key trùng. Đây là khác biệt nghiệp vụ cần cân nhắc.

Nếu cần Map mutable, viết `new HashMap<>(Map.of(...))`; nếu cần insertion order, cân nhắc `LinkedHashMap` và thêm phần tử bằng các statements rõ ràng.

## 26. Ví dụ runnable 10 — Set/Map factory và ngoại lệ về trùng/null

Tạo tệp **`CollectionFactoryRulesDemo.java`**:

~~~java
import java.util.List;
import java.util.Map;
import java.util.Set;

public class CollectionFactoryRulesDemo {
    public static void main(String[] args) {
        List<String> names = List.of("A", "A");
        Set<String> flags = Set.of("READ", "WRITE");
        Map<String, Integer> scores =
                Map.of("An", 10, "Binh", 20);

        System.out.println("list=" + names);
        System.out.println("flags contain READ="
                + flags.contains("READ"));
        System.out.println("score An=" + scores.get("An"));

        try {
            Set.of("A", "A");
        } catch (IllegalArgumentException ex) {
            System.out.println("duplicate set="
                    + ex.getClass().getSimpleName());
        }

        try {
            Map.of("x", 1, "x", 2);
        } catch (IllegalArgumentException ex) {
            System.out.println("duplicate map="
                    + ex.getClass().getSimpleName());
        }

        try {
            List.of("A", null);
        } catch (NullPointerException ex) {
            System.out.println("null list="
                    + ex.getClass().getSimpleName());
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 CollectionFactoryRulesDemo.java
java CollectionFactoryRulesDemo
~~~

**Stdout:**

~~~text
list=[A, A]
flags contain READ=true
score An=10
duplicate set=IllegalArgumentException
duplicate map=IllegalArgumentException
null list=NullPointerException
~~~

Ví dụ dùng `contains` và `get` thay vì in trực tiếp Set/Map nên **không phụ thuộc thứ tự iteration**. Đối chiếu các yêu cầu của API trước khi thay double-brace: nếu code cũ cố ý `put` nhiều lần cùng key để cập nhật giá trị, chuyển thẳng thành `Map.of` sẽ đổi hành vi từ overwrite sang exception.

## 27. Cách thay thế 3 — HashMap mutable hoặc LinkedHashMap có thứ tự rõ ràng

Khi cần thêm/sửa entries về sau:

~~~java
Map<String, Integer> scores = new HashMap<>();
scores.put("An", 10);
scores.put("Binh", 20);
scores.put("An", 11);
~~~

Đây là snippet hợp lệ với imports. Dòng cuối **cập nhật key An** thành 11; rất dễ đọc và không tạo anonymous subclass.

Nếu cần bảo đảm **insertion order** khi iterate theo key, dùng `LinkedHashMap` thay vì HashMap:

~~~java
Map<String, Integer> scores = new LinkedHashMap<>();
scores.put("An", 10);
scores.put("Binh", 20);
~~~

Đừng dựa vào thứ tự được in của HashMap hoặc Map.of như một hợp đồng luôn cố định. Khi biến logic của việc khởi tạo thành một constructor/helper có tên, bạn có thể dễ thêm validation hoặc chọn kiểu Map thích hợp.

## 28. Ví dụ runnable 11 — Mutable map có trật tự, không cần subclass

Tạo tệp **`LinkedHashMapAlternativeDemo.java`**:

~~~java
import java.util.LinkedHashMap;
import java.util.Map;

public class LinkedHashMapAlternativeDemo {
    public static void main(String[] args) {
        Map<String, Integer> scores = new LinkedHashMap<>();
        scores.put("An", 10);
        scores.put("Binh", 20);
        scores.put("An", 11);

        System.out.println("scores=" + scores);
        System.out.println("first key="
                + scores.keySet().iterator().next());
        System.out.println("An=" + scores.get("An"));
        System.out.println("class="
                + (scores.getClass() == LinkedHashMap.class));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 LinkedHashMapAlternativeDemo.java
java LinkedHashMapAlternativeDemo
~~~

**Stdout:**

~~~text
scores={An=11, Binh=20}
first key=An
An=11
class=true
~~~

`LinkedHashMap` ở đây sử dụng mặc định **insertion-order iteration**; việc cập nhật lại value của key An không chuyển An xuống cuối thứ tự insertion. Đây là hành vi rõ ràng hơn việc phụ thuộc vào một lần chạy HashMap.

Code dùng statements bình thường: `new`, các lệnh `put`, rồi sử dụng kết quả. Không có anonymous subclass hoặc instance initializer bị giấu sau hai cặp ngoặc.

## 29. Cách thay thế 4 — factory method có tên cho dữ liệu phải tính toán

Nếu dữ liệu được tạo bằng nhiều nhánh, nhiều vòng lặp hoặc cần validation, thay vì nhét logic vào anonymous initializer:

~~~java
Map<String, Integer> scores = new HashMap<String, Integer>() {{
    put("A", calculateA());
    put("B", calculateB());
}};
~~~

đây chỉ là **snippet ý tưởng**, giả định methods `calculateA()`/`calculateB()` tồn tại.

Cách diễn đạt rõ hơn là **factory có tên**:

~~~java
static Map<String, Integer> buildScores(int a, int b) {
    if (a < 0 || b < 0) {
        throw new IllegalArgumentException("negative score");
    }

    Map<String, Integer> result = new LinkedHashMap<>();
    result.put("A", a);
    result.put("B", b);
    return Map.copyOf(result);
}
~~~

Đây là method minh họa hợp lệ trong một class có imports. Nó mô tả:

- Hai đầu vào được validate trước khi công bố kết quả.
- Có Map mutable tạm trong phạm vi method.
- API trả về **unmodifiable Map snapshot** bằng Map.copyOf.
- `Map.copyOf` không cam kết giữ insertion order của LinkedHashMap, nên không in thứ tự entries của kết quả như một yêu cầu.

Nếu yêu cầu insertion order ở cả API trả về, có thể trả `Collections.unmodifiableMap(new LinkedHashMap<>(result))`; view đó được bảo vệ vì wrapper giữ một **copy riêng** không bị caller nắm mutable reference trong code này.

## 30. Ví dụ runnable 12 — factory tạo map dữ liệu có validation

Tạo tệp **`NamedFactoryAlternativeDemo.java`**:

~~~java
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;

public class NamedFactoryAlternativeDemo {
    static Map<String, Integer> buildScores(int a, int b) {
        if (a < 0 || b < 0) {
            throw new IllegalArgumentException("negative score");
        }

        Map<String, Integer> values = new LinkedHashMap<>();
        values.put("A", a);
        values.put("B", b);

        return Collections.unmodifiableMap(
                new LinkedHashMap<>(values));
    }

    public static void main(String[] args) {
        Map<String, Integer> scores = buildScores(5, 9);
        System.out.println("scores=" + scores);

        try {
            buildScores(-1, 9);
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid=" + ex.getMessage());
        }

        try {
            scores.put("C", 3);
        } catch (UnsupportedOperationException ex) {
            System.out.println("immutable structure="
                    + ex.getClass().getSimpleName());
        }

        System.out.println("after=" + scores);
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 NamedFactoryAlternativeDemo.java
java NamedFactoryAlternativeDemo
~~~

**Stdout:**

~~~text
scores={A=5, B=9}
invalid=negative score
immutable structure=UnsupportedOperationException
after={A=5, B=9}
~~~

`Collections.unmodifiableMap` tạo **unmodifiable view** của Map được truyền vào; ta tạo hẳn một bản `new LinkedHashMap<>(values)` riêng trước khi bọc nên không còn biến mutable nào khác trong method giữ map gốc ấy. Nhờ đó output và insertion order được kiểm soát trong phạm vi ví dụ.

Một unmodifiable view **không mặc nhiên deep-copy mutable values**. Nếu values của map là `List<MutableItem>`, cần thiết kế snapshot phù hợp cho phần tử/lồng sâu; xem phần tiếp theo.

## 31. Cách thay thế không đồng nghĩa deep immutability

Một lỗi chuyển đổi thường gặp: thay double-brace bằng `Map.of` rồi khẳng định **toàn bộ object graph bất biến**.

~~~java
List<String> editableTags = new ArrayList<>();
editableTags.add("A");

Map<String, List<String>> view =
        Map.of("tags", editableTags);
~~~

Đây là snippet hợp lệ. `view.put(...)` bị từ chối, nhưng `editableTags.add("B")` vẫn làm `view.get("tags")` chứa B vì **map giữ reference tới list mutable**.

Khi cần snapshot ổn định, sao chép phần thuộc ownership:

~~~java
Map<String, List<String>> snapshot =
        Map.of("tags", List.copyOf(editableTags));
~~~

Nếu các phần tử là `String` immutable, `List.copyOf` tách mutation cấu trúc của list nguồn. Với phần tử mutable, vẫn cần defensive element copy hoặc immutable representation riêng.

**Không nên quảng bá `List.of`, `Map.of`, `Collections.unmodifiableList` là deep immutability không điều kiện.** Đó là các hợp đồng unmodifiable ở cấp collection và các khác biệt về snapshots/views, không phải clone toàn bộ objects.

## 32. Ví dụ runnable 13 — Map.unmodifiable không đóng băng list value

Tạo tệp **`NestedMutableValueDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

public class NestedMutableValueDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>();
        source.add("A");

        Map<String, List<String>> shared =
                Map.of("tags", source);
        Map<String, List<String>> snapshot =
                Map.of("tags", List.copyOf(source));

        System.out.println("shared before="
                + shared.get("tags"));
        System.out.println("snapshot before="
                + snapshot.get("tags"));

        source.add("B");

        System.out.println("shared after="
                + shared.get("tags"));
        System.out.println("snapshot after="
                + snapshot.get("tags"));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 NestedMutableValueDemo.java
java NestedMutableValueDemo
~~~

**Stdout:**

~~~text
shared before=[A]
snapshot before=[A]
shared after=[A, B]
snapshot after=[A]
~~~

Kết quả cho thấy việc trả một Map unmodifiable không bảo đảm list bên trong cũng là bản sao. Với dữ liệu `String`, `List.copyOf(source)` đủ để tạo một snapshot không đổi cấu trúc, nếu caller không có mutable reference khác tới list bên trong snapshot.

## 33. Nhược điểm 10 — tính hợp lệ của phần được capture

Vì double-brace tạo anonymous class, nó tuân điều kiện capture các **local variables và parameters final/effectively final** giống những anonymous classes khác.

~~~java
int value = 5;
List<Integer> numbers = new ArrayList<Integer>() {{
    add(value);
}};
~~~

Đây là snippet hợp lệ trong method nếu `value` không bị gán lại.

Nhưng nếu cùng method thêm `value++;`, biến `value` không effectively final, và **anonymous initializer không được capture nó**. Đây là lỗi compile-time.

Với `new ArrayList<>(List.of(value))`, không có anonymous class capture `value`; biểu thức dùng ngay giá trị hiện tại của biến. Điều đó có thể thuận tiện hơn khi biến value được cập nhật sau khi tạo list.

**Cảnh báo:** không có nghĩa named constructor `new ArrayList<>(...)` tự snapshot mọi mutable elements. Nó chỉ tránh **quy tắc capture phát sinh do anonymous class** và tạo list container theo hợp đồng constructor.

## 34. Ví dụ runnable 14 — gán lại biến vẫn dùng được khi bỏ anonymous class

Tạo tệp **`NoCaptureNeededDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class NoCaptureNeededDemo {
    public static void main(String[] args) {
        int value = 5;
        List<Integer> first =
                new ArrayList<>(List.of(value));

        value = 8;
        List<Integer> second =
                new ArrayList<>(List.of(value));

        System.out.println("first=" + first);
        System.out.println("second=" + second);
        System.out.println("current value=" + value);
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 NoCaptureNeededDemo.java
java NoCaptureNeededDemo
~~~

**Stdout:**

~~~text
first=[5]
second=[8]
current value=8
~~~

Biến `value` được gán lại bình thường vì ở đây không có anonymous class/lambda capture nó. Mỗi constructor nhận dữ liệu từ giá trị tại thời điểm gọi.

Nếu thay bằng anonymous initializer trực tiếp tham chiếu `value` trong method có lần gán lại này, compiler sẽ từ chối. Đây là một **chi phí không cần thiết** khi mục tiêu chỉ là điền primitive value vào collection.

## 35. Khi nào một anonymous subclass là có chủ đích?

Anonymous subclass **không tự xấu**. Nó là một cơ chế Java hợp lệ khi bạn thật sự cần:

- Override behavior của superclass tại điểm sử dụng.
- Tạo implementation ngắn của interface nhiều abstract methods.
- Có instance fields/helper methods phục vụ một callback riêng.
- Chọn đúng `this` và superclass behavior của anonymous instance.

Điểm đáng tránh là dùng subclassing **chỉ** để rút ngắn:

~~~java
new HashMap<String, Integer>() {{
    put("a", 1);
    put("b", 2);
}}
~~~

nếu điều muốn diễn đạt chỉ là “một Map chứa hai entries”. Trong trường hợp ấy, Map factory/ordinary constructor nói thẳng mục đích hơn và tránh nhiều hệ quả phụ của subclassing.

**Tiêu chí quyết định:** bạn muốn một **kiểu hành vi mới** hay chỉ muốn **dữ liệu có sẵn trong một collection**? Nếu chỉ muốn dữ liệu, hai cặp ngoặc thường là công cụ không tương xứng.

## 36. Danh sách thay thế theo yêu cầu cụ thể

| Yêu cầu thực tế | Gợi ý Java 17 | Lưu ý |
| --- | --- | --- |
| List vài String, không cần sửa | `List.of("A","B")` | Không nhận null |
| List mutable với dữ liệu ban đầu | `new ArrayList<>(List.of("A","B"))` | Đúng ArrayList class |
| List mutable và cho phép null | `new ArrayList<>(Arrays.asList("A",null))` | Tránh List.of vì null |
| Empty mutable list | `new ArrayList<>()` | Đơn giản, không subclass |
| Set không sửa, phần tử duy nhất | `Set.of("READ","WRITE")` | Trùng/null bị từ chối |
| HashSet mutable | `new HashSet<>(Set.of("READ","WRITE"))` | Không bảo đảm iteration order |
| Map nhỏ không sửa | `Map.of("a",1,"b",2)` | Không null/key trùng; iteration order unspecified |
| Map lớn không sửa | `Map.ofEntries(Map.entry(...), ...)` | Chú ý null/duplicates |
| HashMap mutable | `new HashMap<>(Map.of("a",1))` | Có thể `put` sau |
| Map cần insertion order | `LinkedHashMap` + statements | Kiểm soát iteration |
| Tạo theo điều kiện hoặc nhiều bước | Method factory có tên | Dễ validate và test |
| Cần snapshot unmodifiable từ existing list | `List.copyOf(existing)` | Không deep-copy mutable elements |
| Muốn unmodifiable view theo insertion order | `Collections.unmodifiableMap(new LinkedHashMap<>(source))` | View giữ một copy riêng |
| Domain object có nhiều fields, invariants | Builder/constructor/factory | Không nhét logic vào initializer vô danh |
| Cần một anonymous behavior thực sự | Anonymous class/lambda | Không dùng double-brace chỉ như data literal |

Không chọn theo độ ngắn của cú pháp **mà bỏ qua mutability, null policy, equality và iteration order**.

## 37. Ví dụ thay thế có nguyên tắc: một domain object bất biến

Khi có nhiều trường và validation, thay vì double-brace vào một Map “chứa mọi thứ”, dùng một kiểu rõ ràng.

Tạo tệp **`ImmutableProfileDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

final class Profile {
    private final String name;
    private final List<String> roles;

    private Profile(Builder builder) {
        if (builder.name == null || builder.name.isBlank()) {
            throw new IllegalArgumentException("name rỗng");
        }
        name = builder.name;
        roles = List.copyOf(builder.roles);
    }

    static class Builder {
        private String name;
        private final List<String> roles = new ArrayList<>();

        Builder name(String value) {
            name = Objects.requireNonNull(value, "name");
            return this;
        }

        Builder addRole(String role) {
            roles.add(Objects.requireNonNull(role, "role"));
            return this;
        }

        Profile build() {
            return new Profile(this);
        }
    }

    String describe() {
        return name + roles;
    }
}

public class ImmutableProfileDemo {
    public static void main(String[] args) {
        Profile.Builder builder = new Profile.Builder()
                .name("An")
                .addRole("reader");

        Profile first = builder.build();
        builder.addRole("editor");
        Profile second = builder.build();

        System.out.println("first=" + first.describe());
        System.out.println("second=" + second.describe());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 ImmutableProfileDemo.java
java ImmutableProfileDemo
~~~

**Stdout:**

~~~text
first=An[reader]
second=An[reader, editor]
~~~

Builder là một **static nested class có tên**, được thiết kế để thu thập dữ liệu trước khi tạo Profile. Constructor Profile validate name và tạo unmodifiable snapshot của roles. Nếu Builder tiếp tục nhận roles mới, Profile cũ không đổi.

Đây là giải pháp thích hợp cho **domain data có invariant**, chứ không phải vì mọi collection phải dùng builder. Với chỉ hai String constants, `List.of` đơn giản hơn.

## 38. Chi phí hiệu năng: đánh giá đúng mức

Double-brace có thể làm chương trình có thêm một anonymous class declaration thay vì dùng trực tiếp ArrayList/HashMap. Điều đó có thể tác động tới:

- Class metadata và class loading.
- Code size, reflection/introspection và debugging.
- Một số khả năng tối ưu hóa hoặc serialization của runtime/framework.
- Lifetime của những objects được capture nếu chúng được giữ lâu.

Nhưng **không có quy tắc** “double-brace luôn chậm gấp N lần” hoặc “mỗi phần tử thêm vào tốn một class”. Hiệu năng thực tế phụ thuộc call sites, JIT, runtime, garbage collection, class loader, số lượng objects và workload.

Để tối ưu, hãy đo bằng profiler/JMH nếu cần. **Lý do bỏ double-brace thường mạnh nhất là đúng semantics, readability và tránh type/lifecycle surprises**, chứ không phải một con số hiệu năng không được đo.

Các factory methods như `List.of` có thể cho phép implementation tối ưu hóa riêng, nhưng Java không yêu cầu một runtime object layout hay identity nhất định. Đừng viết code phụ thuộc vào `getClass().getName()` của List.of.

## 39. Rủi ro trong test và khi duy trì code cũ

Nếu gặp double-brace trong codebase cũ, đừng thay máy móc mọi chỗ thành `List.of` hoặc `Map.of` mà chưa xem behavior.

Trước hết xác nhận:

1. **Collection có bị sửa sau construction không?** Nếu có, cần mutable alternative.
2. **Có null elements/keys/values không?** Factory of/copyOf có chính sách null chặt hơn.
3. **Có duplicate keys/entries không?** Map.of/Set.of có thể ném exception nơi HashMap/HashSet trước đây không ném.
4. **Có phụ thuộc iteration order không?** Chọn LinkedHashMap/LinkedHashSet hoặc List thích hợp.
5. **Có capture outer object hoặc local variable không?** Dọn dependency đó nếu không cần.
6. **Có override method hoặc thêm field trong anonymous body không?** Khi ấy đây có thể là anonymous subclass có mục đích, không chỉ khởi tạo dữ liệu.
7. **Có serialization không?** Test object graph thực tế.
8. **Có framework phụ thuộc runtime subclass không?** Kiểm tra mapping/serialization cụ thể.
9. **Có initialization side effects không?** Chuyển chúng sang đường thực thi có tên, kiểm tra exception safety.
10. **Có equality hoặc identity-sensitive code không?** Việc loại anonymous subtype có thể đổi kết quả của `getClass()`/custom equals.

**Kiểm thử hai chiều:** nếu thay sang unmodifiable list, thử mutation để biết caller có đang cần sửa dữ liệu. Nếu thay sang mutable list, bảo đảm caller không vô tình làm lộ internal representation.

## 40. Checklist rà soát một biểu thức double-brace

Khi thấy `new T(args) {{ ... }}` trong code:

- T có phải class có thể kế thừa, constructor args có accessible không?
- Cặp ngoặc ngoài là anonymous class body hay có ngữ nghĩa khác?
- Cặp ngoặc trong có phải instance initializer chạy lúc `new` không?
- Có field/method override thật sự cần anonymous subclass không?
- Có thể thay bằng `List.of`, `Set.of`, `Map.of` không?
- Collection đích cần mutable hay unmodifiable?
- Có null/duplicates/order requirements không?
- Có instance context và body cần `Outer.this` không?
- Có captured local variables/parameters final/effectively final không?
- Có nguy cơ giữ Outer hoặc dependency lớn reachable quá lâu không?
- Object có cần được serialize không? Các captured references có serializable không?
- Runtime class khác exact base class có làm framework/test hỏng không?
- `equals` của domain class có phụ thuộc exact runtime type không?
- Instance initializer có side effects, I/O hoặc validation phức tạp không?
- Có thích hợp đưa code sang một factory có tên và test riêng không?
- Nếu đã đổi code, tests có bảo toàn semantics về dữ liệu và mutation không?

## 41. Bài tập tự luyện

**Câu 1.** Trong `new ArrayList<String>() {{ add("A"); }}`, cặp ngoặc thứ nhất và thứ hai mang nghĩa gì?

**Câu 2.** `getClass()==ArrayList.class` của list double-brace có đúng không? `instanceof ArrayList` thì sao?

**Câu 3.** Một biểu thức double-brace trong factory được gọi ba lần. Có ba anonymous classes hay ba objects từ một declaration?

**Câu 4.** Hai biểu thức double-brace ở hai vị trí source khác nhau có bắt buộc cùng runtime class không?

**Câu 5.** Vì sao double-brace tạo trong instance method có thể giữ enclosing Owner object còn reachable?

**Câu 6.** Viết trong static method có tự động khắc phục nhược điểm anonymous subclass không?

**Câu 7.** Vì sao một subclass của ArrayList có thể `instanceof Serializable` nhưng `ObjectOutputStream.writeObject` vẫn thất bại?

**Câu 8.** Trong instance initializer double-brace, `this` trỏ object nào?

**Câu 9.** `List<String> a = List.of("X");` có gọi `a.add("Y")` được không?

**Câu 10.** Dùng cú pháp Java 17 nào để tạo một ArrayList mutable chứa X, Y mà không khai anonymous subclass?

**Câu 11.** `Set.of("A","A")` làm gì? Còn HashSet được add A hai lần thì sao?

**Câu 12.** `Map.of("x",1,"x",2)` khác gì `HashMap.put("x",1); put("x",2);`?

**Câu 13.** Vì sao không nên in `Map.of("a",1,"b",2)` rồi dùng thứ tự chuỗi đó làm một expected stdout bất biến?

**Câu 14.** Nếu cần giữ insertion order khi iterate Map, chọn collection nào?

**Câu 15.** Một custom list so `getClass()` trong `equals`. Anonymous subclass có thể tạo bất ngờ nào?

**Câu 16.** Double-brace có làm list immutable hoặc thread-safe không?

**Câu 17.** `Map.of("tags", mutableList)` có deep-copy list không?

**Câu 18.** Nếu anonymous initializer sửa audit log rồi ném exception, audit log có được rollback tự động không?

**Câu 19.** Muốn capture biến `int n` trong double-brace initializer, nhưng method sau đó viết `n++`. Có compile được không?

**Câu 20.** Nếu dùng `new ArrayList<>(List.of(n))`, method có thể gán lại n sau khi tạo list không?

**Câu 21.** Khi cần validation nhiều trường và trả immutable domain object, dùng double-brace HashMap hay constructor/builder rõ kiểu?

**Câu 22.** `List.copyOf(source)` có deep-copy các mutable elements không?

**Câu 23.** Vì sao không nên dựa vào tên binary `Outer$1` của anonymous class để làm ID?

**Câu 24.** Khi migration double-brace sang List.of, hai nhóm test quan trọng cần chạy là gì?

### Đáp án và giải thích

1. Ngoài là **anonymous subclass body**, trong là **instance initializer block**.
2. `getClass()==ArrayList.class` false; `instanceof ArrayList` true nếu subclass hợp lệ.
3. Ba objects từ cùng anonymous class declaration ở một vị trí source, không mặc định ba classes.
4. Không; hai anonymous declarations khác nhau tương ứng hai types khác nhau.
5. Body có thể tham chiếu enclosing instance, và collection được giữ lâu có thể giữ reference đó reachable.
6. Không. Static method không có implicit Outer instance, nhưng anonymous subclass/initializer vẫn tồn tại.
7. Vì object graph được serialize có thể chứa captured outer hoặc fields không serializable.
8. Anonymous collection object; `Outer.this` mới chỉ enclosing Outer khi hợp lệ.
9. Không; List.of trả unmodifiable list, add ném `UnsupportedOperationException`.
10. `new ArrayList<>(List.of("X","Y"))`.
11. Set.of ném `IllegalArgumentException`; HashSet chỉ giữ A một lần, `add` thứ hai trả false.
12. Map.of từ chối duplicate key bằng `IllegalArgumentException`; HashMap.put sau sẽ ghi đè value.
13. Map.of không bảo đảm iteration order trong contract.
14. `LinkedHashMap` mặc định duyệt theo insertion order.
15. Một list có cùng contents có thể không equal vì anonymous runtime subclass khác exact class.
16. Không; phụ thuộc collection và synchronization thực tế.
17. Không; map chỉ giữ reference tới list mutable.
18. Không; side effects bên ngoài vẫn có thể tồn tại.
19. Không; n không effectively final do phép tăng.
20. Có; không có anonymous class capture n ở đây.
21. Constructor/builder/factory có validation và typed invariant rõ ràng.
22. Không. Nó snapshot cấu trúc list nhưng không tự clone mutable elements.
23. Compiler-generated names không phải business contract ổn định.
24. Kiểm tra **dữ liệu và thứ tự yêu cầu**, đồng thời **mutability/null/duplicate behavior**; bổ sung serialization/runtime type nếu hệ thống có dùng.

## 42. Bảng đối chiếu ngắn: trước và sau refactor

| Trước: double-brace | Sau: Java 17 | Lợi ích / thay đổi phải nhớ |
| --- | --- | --- |
| `new ArrayList<String>() {{add("A");add("B");}}` | `new ArrayList<>(List.of("A","B"))` | Giữ tính mutable và List ordering; không subclass |
| `new ArrayList<String>() {{add("A");}}` | `List.of("A")` | Chuyển thành unmodifiable list, không tương đương mutation |
| `new HashSet<String>() {{add("A");add("B");}}` | `Set.of("A","B")` | Không sửa được; từ chối duplicates/null |
| `new HashMap<String,Integer>() {{put("a",1);put("b",2);}}` | `Map.of("a",1,"b",2)` | Không sửa được; iteration order không cam kết |
| `new HashMap<String,Integer>() {{put("a",1);}}` | `new HashMap<>(Map.of("a",1))` | Giữ mutable HashMap, không anonymous subclass |
| Double-brace Map có nhiều bước | Named factory với `put` statements | Dễ kiểm tra side effects và validation |
| Double-brace list trong domain object | Builder/constructor + defensive copy | Invariants và ownership rõ |

**Không thay đổi contract âm thầm.** Nếu caller đang cần mutate một List, `List.of` không phải drop-in replacement. Nếu dữ liệu có null, `List.of` có thể ném `NullPointerException`. Nếu Set/Map có duplicates, of-factories có thể ném `IllegalArgumentException`. Nếu cần iteration order, kiểm tra loại collection trả về trước khi chọn.

## 43. Tài liệu chính thức cho Java 17

- [JLS 17 §15.9 — Class Instance Creation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.9): cú pháp `new` và anonymous creation.
- [JLS 17 §15.9.5 — Anonymous Class Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.9.5): vì sao cặp ngoặc ngoài tạo subclass vô danh.
- [JLS 17 §8.6 — Instance Initializers](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.6): ý nghĩa cặp ngoặc trong.
- [JLS 17 §12.5 — Creation of New Class Instances](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.5): thứ tự construction/initialization.
- [JLS 17 §8.1.3 — Inner Classes and Enclosing Instances](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.3): enclosing-instance behavior.
- [JLS 17 §4.12.4 — final Variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.12.4): quy tắc captured final/effectively final.
- [Java SE 17 — ArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html): constructors, List equality, mutability.
- [Java SE 17 — List.of / List.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#of(E...)): factory list không cho structural mutation, xử lý null.
- [Java SE 17 — Set.of](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html#of(E...)): rejects null/duplicates.
- [Java SE 17 — Map.of](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#of()): unmodifiable map factories.
- [Java SE 17 — Map.ofEntries](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#ofEntries(java.util.Map.Entry...)): tạo maps từ nhiều entries.
- [Java SE 17 — Collections.unmodifiableMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableMap(java.util.Map)): view không cho mutation.
- [Java SE 17 — LinkedHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html): iteration order khi cần.
- [Java SE 17 — Serializable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Serializable.html): serialization marker và object graph.
- [Java SE 17 — ObjectOutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectOutputStream.html): ghi object graph và lỗi serialization.
- [Java SE 17 — Class.isAnonymousClass](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#isAnonymousClass()): kiểm tra anonymous runtime type.

## 44. Tổng kết

**Hai cặp ngoặc nhọn không phải cú pháp literal cho collection**. Chúng tạo **anonymous subclass** và chạy **instance initializer**, nên mang theo chi phí/nguy cơ không cần thiết nếu mục đích chỉ là dữ liệu:

1. Runtime class không còn chính xác là `ArrayList.class`/`HashMap.class`, có thể ảnh hưởng reflection/framework và custom equality.
2. Trong instance context có thể giữ **enclosing instance** hoặc captured references lâu hơn dự kiến.
3. Serialization có thể thất bại nếu object graph chứa references không serializable.
4. Initializer có thể có side effects hoặc ném exception ngay lúc creation.
5. Final/effectively-final capture rules áp dụng, dù bạn chỉ muốn đưa một giá trị đang thay đổi vào list.
6. Nó **không** tạo immutability hay thread safety và cũng không tự bảo đảm hiệu năng tốt hơn.
7. Cú pháp khiến người đọc phải hiểu cơ chế subclass/initializer thay vì nhìn rõ ý định tạo collection dữ liệu.

**Cách chọn thực dụng:** nếu dữ liệu không cần sửa, dùng `List.of`, `Set.of`, `Map.of` khi semantics về null, duplicate, order phù hợp. Nếu cần mutable ArrayList/HashMap, dùng `new ArrayList<>(...)`/`new HashMap<>(...)` hoặc các lệnh `add`/`put` bình thường. Nếu tạo dữ liệu theo logic nhiều bước hoặc có validation, dùng **factory/Builder có tên**. Chỉ dùng anonymous subclass khi **thực sự cần một subtype có hành vi riêng**, không chỉ để viết ngắn vài dòng khởi tạo.
