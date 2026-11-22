# Vai trò của getClass() trong equals(), clone() và chẩn đoán

## 1. getClass() cho biết điều gì?

**Object.getClass()** là phương thức public final của java.lang.Object, có trên mọi đối tượng Java không null. Nó trả về một đối tượng **Class** biểu diễn **lớp thực tế tại thời điểm chạy (runtime class)** của đối tượng đang nhận lời gọi, kể cả khi biến đang được khai báo bằng kiểu cha hoặc interface.

~~~java
Object value = "Java";
Class<?> actual = value.getClass();
System.out.println(actual == String.class); // true
~~~

Biến value có kiểu khai báo Object nhưng đối tượng đang trỏ tới là String. Vì vậy getClass() trả Class của String. Kết quả **không phụ thuộc vào kiểu khai báo của biến tham chiếu**.

Một số điểm nền tảng:

- Class là đối tượng mô tả một kiểu trong môi trường chạy Java. Có thể dùng để kiểm tra tên, modifier, superclass, interface, annotation hay phục vụ reflection.
- Với một đối tượng đang tồn tại, getClass() trả lớp thực tế của chính đối tượng đó. Các lần gọi không làm thay đổi lớp đối tượng.
- getClass() là final nên không thể ghi đè để giả mạo lớp trả về bằng một phương thức có cùng chữ ký.
- Gọi getClass() trên biến tham chiếu **null** gây NullPointerException, vì không có đối tượng để gọi phương thức.
- Một lớp có thể được nạp bởi các class loader khác nhau. Danh tính Class không chỉ là tên chuỗi của lớp; hai kiểu trùng tên nhưng do class loader khác nhau định nghĩa có thể là những Class khác nhau.

Ba ứng dụng thường gặp trong hợp đồng đối tượng là: **kiểm tra kiểu chính xác trong equals()**, **xác minh kiểu runtime khi sao chép qua clone()**, và **chẩn đoán đối tượng hoặc hệ thống reflection/proxy**. getClass() tự nó không quyết định hai đối tượng bằng nhau, không thực hiện clone và không giải thích nguyên nhân lỗi.

## 2. getClass() trong equals(): so sánh đúng lớp runtime

Khi ghi đè equals(Object), lập trình viên phải xác định liệu hai đối tượng thuộc các kiểu khác nhau có được phép coi là bằng nhau hay không.

Một mẫu phổ biến để chỉ chấp nhận **đúng cùng lớp runtime**:

~~~java
@Override
public boolean equals(Object obj) {
    if (this == obj) {
        return true;
    }
    if (obj == null || getClass() != obj.getClass()) {
        return false;
    }
    Account other = (Account) obj;
    return id.equals(other.id);
}
~~~

Đây là **trích đoạn** nằm trong lớp Account có trường id khác null và không thay đổi; chưa phải chương trình độc lập.

Cách triển khai trên hoạt động theo thứ tự:

1. Cùng tham chiếu this == obj: trả true (phản xạ, và tránh kiểm tra thừa).
2. obj null: trả false, không gọi obj.getClass() trên null.
3. getClass() khác obj.getClass(): trả false dù hai đối tượng có cùng trường id.
4. Chỉ sau khi xác định lớp runtime giống nhau mới ép kiểu và so sánh các trường quyết định equality.
5. hashCode phải nhất quán với equals: mọi cặp equals true bắt buộc có hash bằng nhau.

Trong mã này, **getClass() != obj.getClass() kiểm tra danh tính lớp**, khác với so sánh chuỗi tên lớp. Hai đối tượng từ cùng lớp có cùng đối tượng Class, còn hai lớp khác nhau sẽ không có cùng Class.

### getClass() so với instanceof

Hai kiểu kiểm tra có ý nghĩa khác nhau:

| Cách kiểm tra | Điều được chấp nhận | Hệ quả |
| --- | --- | --- |
| obj instanceof Account | Account và các đối tượng thuộc lớp con của Account | Hỗ trợ quan hệ kiểu con |
| obj != null && getClass() == obj.getClass() | Chỉ đối tượng có đúng lớp runtime như this | Loại lớp con khác runtime class |
| Account.class == obj.getClass() | Chỉ đúng lớp Account được nhắc trực tiếp | Không tương đương getClass() của this khi chạy trong lớp con |

**Ví dụ:** một đối tượng PremiumAccount kế thừa Account là instanceof Account, nhưng PremiumAccount.class khác Account.class. Vì vậy getClass cho hai đối tượng thuộc hai lớp này khác nhau.

Nếu equals của lớp cha dùng instanceof và chỉ so sánh id, còn lớp con bổ sung trạng thái quan trọng rồi ghi đè equals, rất dễ rơi vào lỗi **mất tính đối xứng**: lớp cha xem đối tượng lớp con là bằng nhau, nhưng lớp con từ chối lớp cha. Kiểm tra đúng lớp bằng getClass() có thể giúp định nghĩa một chính sách “khác lớp thì khác giá trị” rõ ràng và tránh một nhóm lỗi như vậy.

Tuy nhiên **getClass() không tự động làm equals đúng**: vẫn phải kiểm tra tính đối xứng, bắc cầu, nhất quán và quan hệ với hashCode. Đặc biệt khi lớp cha cho phép subclass mở rộng các trường mang ý nghĩa equality, việc để subclass kế thừa nguyên equals mà không bổ sung quy tắc có thể khiến các đối tượng lớp con bị coi bằng nhau dù các trường mới khác nhau.

### Khi nào không nên dùng kiểm tra lớp chính xác?

Nếu mô hình nghiệp vụ chủ ý coi các đối tượng từ các lớp con khác nhau là cùng một giá trị dựa trên giao diện chung, kiểm tra getClass() sẽ **quá chặt**. Một quy tắc dựa trên instanceof, interface, định danh hoặc thiết kế value object thống nhất có thể phù hợp hơn, nhưng phải bảo đảm đối xứng và bắc cầu trong toàn bộ hệ phân cấp.

Ví dụ các lớp proxy runtime (một số ORM hoặc thư viện sinh lớp proxy động) có thể là lớp con của kiểu miền. getClass() trên proxy trả **lớp proxy thực tế**, khác với lớp thực thể ban đầu. Nếu equals dùng strict getClass, entity và proxy của nó có thể so sánh false ngay cả khi biểu diễn cùng một bản ghi. Trường hợp này cần tuân theo hợp đồng equality và API nhận diện lớp thực thể do framework cụ thể cung cấp; không nên tự giả định mọi proxy có cùng hành vi.

**Nguyên tắc:** lựa chọn getClass hay instanceof dựa vào ý nghĩa bình đẳng và chiến lược kế thừa của lớp, không phải vì một câu thần chú “getClass luôn tốt hơn”.

## 3. getClass() và hợp đồng hashCode

Giả sử hai đối tượng phải cùng **lớp runtime và cùng id** mới equals:

~~~java
@Override
public int hashCode() {
    return java.util.Objects.hash(getClass(), id);
}
~~~

Công thức này nhất quán với equals ở phần 2: nếu hai đối tượng có cùng runtime class và id, chúng có cùng giá trị đầu vào để băm.

Tuy nhiên, **không bắt buộc** hashCode phải thêm getClass() để hợp đồng đúng. Dùng id.hashCode() cũng có thể hợp lệ nếu id không null, vì hai đối tượng equals true luôn có id bằng nhau; những đối tượng khác lớp nhưng id giống nhau có thể va chạm hash, và va chạm là hợp lệ.

Vì thế:

- Thêm getClass vào hash có thể giúp phân tán theo kiểu khi có nhiều lớp dùng cùng id.
- Bỏ getClass khỏi hash **không tự động là lỗi** nếu vẫn bảo đảm equals true kéo theo cùng hash.
- Không dùng getClass().getName() chỉ để suy ra danh tính lớp; dùng chính Class trong những thiết kế cần phân biệt runtime type.
- Nếu equals theo chính sách chấp nhận lớp con bằng lớp cha, phải chọn dữ liệu băm tương thích chính sách ấy; thêm runtime class vào hash có thể làm hai đối tượng equals true nhận hash khác nhau.

Với đối tượng dùng làm khóa HashSet/HashMap, các trường tham gia equality nên ổn định trong suốt thời gian lưu khóa. Class runtime không đổi, nhưng các trường mutable như id nếu bị sửa vẫn có thể làm hash thay đổi và gây khó tìm lại khóa.

## 4. getClass() liên quan gì đến clone()?

Object.clone() là phương thức **protected** của Object. Với lớp có triển khai giao diện marker **Cloneable**, lời gọi super.clone() trong một override hợp lệ thường tạo một đối tượng mới có **đúng lớp runtime của đối tượng nguồn**, và sao chép từng trường theo kiểu **shallow copy**.

Đối với một lớp đơn giản:

~~~java
@Override
public MyType clone() {
    try {
        return (MyType) super.clone();
    } catch (CloneNotSupportedException e) {
        throw new AssertionError(e);
    }
}
~~~

Đoạn này giả định lớp MyType implements Cloneable và không cần thêm xử lý sau khi clone. super.clone() không gọi constructor theo cách thông thường để xây dựng lại toàn bộ object graph.

Một số điều quan trọng:

1. **clone không tự do gọi từ bên ngoài**: Object.clone là protected; lớp có thể mở rộng quyền truy cập bằng override public clone.
2. **Cloneable không có phương thức clone**: đó là marker interface làm Object.clone chấp nhận sao chép; chỉ khai báo implements Cloneable không tự biến clone thành public.
3. **super.clone() tạo một thể hiện mới cùng runtime class**: nếu lời gọi đi qua lớp cha đến một đối tượng lớp con hỗ trợ Cloneable, thể hiện được tạo ra vẫn thuộc lớp con thực tế, không bị cắt xuống thành lớp cha.
4. **Sao chép nông**: trường primitive được chép giá trị; trường tham chiếu được chép tham chiếu, nên cả nguồn và bản sao có thể cùng trỏ vào một List, mảng, hoặc đối tượng mutable.
5. Nếu đối tượng không thực hiện Cloneable mà trực tiếp gọi Object.clone, CloneNotSupportedException sẽ được ném. Mảng Java là trường hợp có hỗ trợ clone và việc clone mảng tạo mảng mới cùng kiểu, nhưng phần tử tham chiếu bên trong vẫn được sao chép nông.

getClass giúp **kiểm tra kiểu thực tế của bản sao**:

~~~java
Object copied = original.clone();
boolean sameRuntimeClass = original.getClass() == copied.getClass();
~~~

Đây là đoạn minh họa đặt trong ngữ cảnh original có một phương thức clone truy cập được.

### Điều gì là bảo đảm, điều gì chỉ là kỳ vọng?

Với **super.clone() của Object**, bản sao có runtime class giống nguồn và các trường được sao chép nông. Nếu lớp **ghi đè clone theo cách riêng** (ví dụ tự khởi tạo một kiểu khác và trả về dưới dạng Object), không thể kết luận mọi phương thức tên clone của mọi lớp Java đều giữ đúng runtime class. Tài liệu Object.clone mô tả các kỳ vọng thông thường như bản sao khác tham chiếu, cùng lớp runtime, thường tương đương về giá trị; các kỳ vọng này không được bắt buộc tuyệt đối đối với mọi override tự định nghĩa.

Ngoài ra:

- Hai đối tượng khác tham chiếu không mặc định equals: nếu lớp kế thừa Object.equals, nó so sánh danh tính nên bản sao cũng không equals nguồn dù mọi trường vừa được copy.
- Bản sao cùng Class không có nghĩa là các đối tượng con được copy độc lập.
- Kiểm tra getClass() bằng nhau không chứng minh dữ liệu bằng nhau, copy đầy đủ, hoặc an toàn khi cùng sửa từ hai luồng.

## 5. Ví dụ Java 17+ hoàn chỉnh: equals, clone và chẩn đoán

Tạo tệp **GetClassContractDemo.java**:

~~~java
import java.util.Arrays;
import java.util.Objects;

public class GetClassContractDemo {
    static class Key {
        private final String id;

        Key(String id) {
            this.id = Objects.requireNonNull(id);
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (obj == null || getClass() != obj.getClass()) {
                return false;
            }
            Key other = (Key) obj;
            return id.equals(other.id);
        }

        @Override
        public int hashCode() {
            return Objects.hash(getClass(), id);
        }
    }

    // Không thêm trường tham gia equality: lớp con chỉ để minh họa kiểu runtime.
    static final class SpecialKey extends Key {
        SpecialKey(String id) {
            super(id);
        }
    }

    static final class CloneBox implements Cloneable {
        private final String name;
        private final int[] numbers;

        CloneBox(String name, int[] numbers) {
            this.name = Objects.requireNonNull(name);
            this.numbers = Objects.requireNonNull(numbers).clone();
        }

        @Override
        public CloneBox clone() {
            try {
                return (CloneBox) super.clone();
            } catch (CloneNotSupportedException e) {
                throw new AssertionError(e);
            }
        }

        CloneBox independentCopy() {
            return new CloneBox(name, numbers);
        }

        void changeFirst(int value) {
            numbers[0] = value;
        }

        int first() {
            return numbers[0];
        }
    }

    public static void main(String[] args) {
        Key first = new Key("A");
        Key second = new Key("A");
        Key subclass = new SpecialKey("A");

        System.out.println("same Class for same type: "
                + (first.getClass() == second.getClass()));
        System.out.println("different Class for subclass: "
                + (first.getClass() != subclass.getClass()));
        System.out.println("first equals second: " + first.equals(second));
        System.out.println("first equals subclass: " + first.equals(subclass));
        System.out.println("subclass equals first: " + subclass.equals(first));
        System.out.println("subclass instanceof Key: "
                + (subclass instanceof Key));
        System.out.println("runtime simple name: "
                + subclass.getClass().getSimpleName());

        CloneBox original = new CloneBox("data", new int[] {10, 20});
        CloneBox shallow = original.clone();
        System.out.println("clone is a new reference: "
                + (original != shallow));
        System.out.println("clone has same Class: "
                + (original.getClass() == shallow.getClass()));
        System.out.println("clone shares array: "
                + (original.numbers == shallow.numbers));

        shallow.changeFirst(99);
        System.out.println("original first after shallow edit: "
                + original.first());

        CloneBox independent = original.independentCopy();
        System.out.println("independent array: "
                + (original.numbers != independent.numbers));
        independent.changeFirst(7);
        System.out.println("original first after independent edit: "
                + original.first());

        System.out.println("class full name: "
                + first.getClass().getName());
        System.out.println("array class: "
                + new int[2].getClass().getName());
        System.out.println("array is array type: "
                + new int[2].getClass().isArray());
    }
}
~~~

Biên dịch và chạy từ thư mục chứa tệp:

~~~bash
javac -encoding UTF-8 GetClassContractDemo.java
java GetClassContractDemo
~~~

**Stdout chính xác:**

~~~text
same Class for same type: true
different Class for subclass: true
first equals second: true
first equals subclass: false
subclass equals first: false
subclass instanceof Key: true
runtime simple name: SpecialKey
clone is a new reference: true
clone has same Class: true
clone shares array: true
original first after shallow edit: 99
independent array: true
original first after independent edit: 99
class full name: GetClassContractDemo$Key
array class: [I
array is array type: true
~~~

**Giải thích kết quả:**

- first và second là hai đối tượng Key riêng nhưng cùng runtime class và id, vì vậy equals trả true.
- subclass là SpecialKey: vẫn là instanceof Key, nhưng runtime class khác Key. Phép equals kế thừa từ Key dùng getClass() nên cả hai chiều Key/SpecialKey đều false; đây là một ví dụ về chính sách equality nghiêm ngặt theo lớp runtime.
- original.clone() qua super.clone() tạo CloneBox mới cùng runtime class. Tuy nhiên, trường numbers của hai bản vẫn cùng tham chiếu một mảng: sửa shallow cũng làm original thấy số 99.
- independentCopy tạo một CloneBox mới từ constructor có sao chép mảng đầu vào. Sau khi sửa bản độc lập, original vẫn giữ phần tử đầu tiên là 99.
- getName() cho lớp lồng tĩnh Key có tên nhị phân gồm dấu $. Kiểu mảng int[] có tên nhị phân JVM dạng [I; isArray() giúp nhận biết đó là kiểu mảng. Tên lớp để chẩn đoán phụ thuộc cấu trúc khai báo, package và class loader thực tế.

Ví dụ dùng riêng lớp Key để minh họa nguyên tắc equality, và CloneBox để minh họa clone. Không nên hiểu rằng mọi class đều phải vừa ghi đè equals vừa hỗ trợ Cloneable.

## 6. Dùng getClass() để chẩn đoán và điều tra lỗi

Khi một đối tượng xuất hiện ở vị trí nhận Object hoặc interface, getClass() giúp xác định **runtime type thực sự**:

~~~java
static void inspect(Object value) {
    if (value == null) {
        System.out.println("null reference");
        return;
    }
    Class<?> type = value.getClass();
    System.out.println("type: " + type.getName());
    System.out.println("simple name: " + type.getSimpleName());
    System.out.println("is array: " + type.isArray());
}
~~~

Đây là phương thức minh họa có thể đặt trong một lớp Java; không phải chương trình độc lập vì thiếu lớp chứa và lời gọi.

Các API đáng biết:

| API | Thông tin | Lưu ý |
| --- | --- | --- |
| obj.getClass() | Đối tượng Class của kiểu runtime | obj phải khác null |
| type.getName() | Tên kiểu theo quy ước JVM/Java | Lớp lồng, mảng có tên đặc thù |
| type.getSimpleName() | Tên ngắn của kiểu | Có thể là chuỗi rỗng với lớp ẩn danh |
| type.getCanonicalName() | Tên chính tắc nếu tồn tại | Một số kiểu local/anonymous không có canonical name |
| type.getSuperclass() | Lớp cha trực tiếp (nếu có) | Interface và Object có thể trả null |
| type.getInterfaces() | Các interface trực tiếp được khai báo | Không tự liệt kê mọi interface kế thừa gián tiếp |
| type.isArray() | Kiểu có phải mảng không | Hữu ích vì tên mảng có dạng JVM |
| type.isInterface() | Kiểu có phải interface không | Hỗ trợ phân loại kiểu khi phản chiếu |

Ví dụ khi một biến kiểu List thực tế chứa ArrayList, getClass có thể giúp nhận ra lớp triển khai ở runtime. Với thư viện tạo proxy hoặc bytecode tăng cường, tên runtime có thể chứa mã sinh tự động; kết quả getClass hỗ trợ chẩn đoán nhưng không nên xem tên sinh tự động là API ổn định.

### getClass() không thay thế instanceof và kiểm tra kiểu an toàn

Nếu chỉ cần biết đối tượng có hỗ trợ một giao diện nào đó, kiểm tra instanceof thường phản ánh đúng mục tiêu hơn:

~~~java
if (value instanceof java.util.List<?> list) {
    System.out.println("size: " + list.size());
}
~~~

Kiểm tra bằng chuỗi như getClass().getName().equals("java.util.ArrayList") dễ bị phụ thuộc triển khai, không xét lớp con, và có thể xử lý sai khi xuất hiện proxy. Dùng instanceof, Class.isInstance hoặc Class.isAssignableFrom phù hợp với mục tiêu kiểm tra khả năng gán kiểu.

### Chẩn đoán lớp và ClassLoader

Một kiểu được định danh bởi **tên nhị phân và class loader định nghĩa nó**. Khi gặp ClassCastException gây ngạc nhiên giữa những tên lớp trông giống nhau, thông tin class loader có thể giúp phân tích:

~~~java
Class<?> type = value.getClass();
ClassLoader loader = type.getClassLoader();
System.out.println("class: " + type.getName());
System.out.println("loader: " + loader);
~~~

Đoạn minh họa; loader có thể là null đối với lớp do bootstrap class loader định nghĩa, nên không gọi loader.toString() mà không kiểm tra null. Chỉ log thông tin lớp và loader ở mức phù hợp với chính sách vận hành, vì tên lớp/loader có thể làm lộ chi tiết triển khai trong log công khai.

Thông tin getClass giúp *đặt câu hỏi đúng*: đây là lớp thật hay proxy, đúng phiên bản và loader không, nó có kế thừa/triển khai đúng kiểu không? Nhưng riêng getClass không chứng minh nguyên nhân của mọi ClassCastException hoặc lỗi serialization/clone.

## 7. Những lỗi thường gặp và cách tránh

### Lỗi 1: Gọi obj.getClass() khi obj có thể null

~~~java
// Nguy cơ NullPointerException:
return getClass() == obj.getClass();
~~~

Cần kiểm tra obj == null trước. Khi muốn kiểm tra hai tham chiếu có cùng danh tính, toán tử == an toàn với null. Khi muốn so giá trị có thể null, dùng Objects.equals hoặc logic phù hợp.

### Lỗi 2: Dùng getClass trong equals rồi quên hashCode

Nếu equals được ghi đè, phải bảo đảm hashCode tương thích: hai đối tượng bằng nhau luôn có cùng hash. getClass không tự thay đổi hashCode của Object hay bảo đảm đúng hợp đồng. Các lớp giá trị nên xác định những trường tham gia equality rồi băm phù hợp.

### Lỗi 3: Coi getClass và instanceof là tương đương

getClass kiểm tra đúng kiểu runtime, còn instanceof chấp nhận kiểu con hoặc triển khai interface. Việc thay thế một cách máy móc có thể đổi nghĩa nghiệp vụ, đặc biệt với hệ phân cấp lớp và proxy runtime.

### Lỗi 4: Nghĩ Cloneable tạo bản sao sâu

implements Cloneable chỉ cho phép Object.clone sao chép theo cơ chế của nó. Nếu chứa mảng, List, Map hay đối tượng con mutable, bản sao qua super.clone thường chia sẻ các tham chiếu ấy. Muốn sao chép độc lập phải xử lý rõ từng thành phần mutable, cân nhắc aliasing hoặc dùng copy constructor/factory.

### Lỗi 5: Nghĩ clone() chỉ có thể trả đúng kiểu runtime

super.clone giữ runtime class trong trường hợp chuẩn. Nhưng một override clone tùy chỉnh có thể dùng logic riêng; không được coi bất kỳ phương thức có tên clone nào cũng được JVM bắt buộc sao y kiểu nguồn. Kiểm tra hợp đồng API cụ thể trước khi ép kiểu và dựa vào kết quả.

### Lỗi 6: Dùng getClass().getName() làm danh tính nghiệp vụ

Tên lớp có thể thay đổi khi refactor, shading, proxy generation hoặc class loader khác nhau. Danh tính doanh nghiệp thường nên dựa trên id hoặc dữ liệu miền. Tên lớp phục vụ phản chiếu và chẩn đoán, không phải khóa nghiệp vụ ổn định.

### Lỗi 7: Dùng constructor reflection để thay Object.clone mà không xét khác biệt

Một thao tác tạo đối tượng mới bằng reflection và gọi constructor **không mặc định** tạo bản sao: nó chạy logic constructor, có thể thiếu tham số, không sao chép trường, và bị ràng buộc truy cập/module. getClass().getDeclaredConstructor().newInstance() không thay thế super.clone hoặc một copy constructor được thiết kế đúng.

## 8. Cách quyết định trong thực tế

| Nhu cầu | Cách tiếp cận |
| --- | --- |
| equals chỉ chấp nhận đúng cùng runtime class | So sánh getClass() sau khi kiểm tra null |
| equals cố ý hỗ trợ lớp con/giao diện chung | Xem xét instanceof và thiết kế hợp đồng toàn bộ phân cấp |
| Hash code tương thích với equals theo lớp và trường | Hash các dữ liệu tương đương, có thể gồm getClass nếu cần |
| Xác minh kiểu bản sao từ super.clone | So sánh getClass giữa nguồn và bản sao |
| Muốn bản sao độc lập của dữ liệu mutable | Sao chép phần tử/đối tượng con thích hợp hoặc dùng copy constructor |
| Gỡ lỗi runtime type/proxy | Ghi getClass().getName(), kiểm tra superclass và loader khi cần |
| Kiểm tra một đối tượng có hỗ trợ interface | instanceof hoặc Class.isInstance/isAssignableFrom |
| Kiểm tra chuỗi tên lớp cho logic nghiệp vụ | Tránh, ưu tiên dữ liệu định danh và API kiểu |

**Checklist trước khi hoàn tất:**

1. Với equals, đã định nghĩa rõ cùng lớp hay khác lớp có được coi bằng nhau chưa? Kiểm tra null, phản xạ, đối xứng, bắc cầu và hashCode.
2. Nếu có lớp con, việc thêm trạng thái equality hoặc dùng proxy có làm đổi kết quả không? Có xung đột với yêu cầu nghiệp vụ không?
3. Nếu clone, đã xác định mức sao chép nông/sâu chưa? Bản sao có chia sẻ cấu trúc mutable không? Có cần copy constructor/factory an toàn hơn không?
4. Nếu dùng getClass để log, đã xử lý null, lớp được sinh động và tính ổn định của tên lớp chưa?
5. Nếu thấy hai đối tượng có cùng getClass, nhớ rằng điều này **không** bảo đảm equals true, cấu trúc bên trong giống nhau hoặc hai đối tượng chia sẻ trạng thái.

## 9. Ghi nhớ

**getClass() cho biết chính xác runtime class của một đối tượng, không phải kiểu khai báo của biến.** Trong equals, nó hỗ trợ chính sách “đúng cùng lớp thì mới được so sánh giá trị”, cần được chọn có ý thức so với instanceof. Trong clone, nó giúp quan sát việc super.clone tạo bản sao cùng runtime class, nhưng việc chia sẻ trường tham chiếu có thể khiến bản sao chỉ là shallow copy. Trong chẩn đoán, getClass là điểm xuất phát hữu ích để nhận diện kiểu, lớp proxy, kiểu mảng và class loader — không thay cho việc thiết kế equality, copy hay xử lý lỗi đúng ngữ cảnh.