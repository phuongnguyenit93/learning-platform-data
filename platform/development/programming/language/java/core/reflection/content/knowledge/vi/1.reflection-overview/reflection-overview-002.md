# Phân biệt thông tin kiểu lúc biên dịch và lúc chạy trong Java

## 1. Mục tiêu

Sau bài học, bạn có thể:
- Phân biệt **kiểu tĩnh (static/compile-time type)** của một biểu thức với **lớp thực tế (runtime class)** của đối tượng mà biểu thức tham chiếu.
- Dự đoán chỗ nào Java kiểm tra kiểu khi biên dịch và chỗ nào JVM phải kiểm tra khi chạy.
- Giải thích vì sao **overload** phụ thuộc kiểu lúc biên dịch, còn **override** phụ thuộc đối tượng lúc chạy.
- Chọn đúng **Class literal**, **getClass()**, **instanceof** và các API Reflection khi cần quan sát kiểu.
- Hiểu giới hạn của Reflection do **type erasure**, và các ngoại lệ như metadata khai báo generic hoặc kiểu phần tử của mảng.

Bối cảnh: Java là ngôn ngữ kiểm tra kiểu tĩnh. Compiler và JVM có vai trò khác nhau, nhưng cùng góp phần thực thi tính an toàn kiểu. Reflection giúp chương trình truy vấn lớp, phương thức, field hoặc kiểu generic được ghi trong metadata ở thời điểm chạy; Reflection không biến mọi thông tin mà compiler từng biết thành dữ liệu có thể truy xuất từ một đối tượng.

## 2. Hai câu hỏi về “kiểu”

Xét khai báo:

~~~java
Animal pet = new Dog();
~~~

Đoạn trên giả định **Dog extends Animal**.

- **Kiểu lúc biên dịch của biểu thức pet:** **Animal**, vì đây là kiểu được khai báo của biến. Compiler dùng nó để kiểm tra phương thức nào có thể gọi, phép gán nào hợp lệ và overload nào được chọn.
- **Lớp thực tế của đối tượng lúc chạy:** **Dog**, vì đối tượng được tạo bằng **new Dog()**. Với tham chiếu khác null, **pet.getClass()** cho đối tượng Class biểu diễn Dog.
- **Một tham chiếu có thể đổi đối tượng:** nếu sau đó **pet = new Cat()** và Cat cũng extends Animal, kiểu khai báo của pet vẫn là Animal, nhưng lớp thực tế mà pet trỏ tới lúc đó là Cat.
- **Không có đối tượng khi null:** biến **Animal pet = null** vẫn có kiểu tĩnh Animal, nhưng **pet.getClass()** sẽ gây NullPointerException.

| Khía cạnh | Lúc biên dịch | Lúc chạy |
| --- | --- | --- |
| Câu hỏi chính | Biểu thức này **được phép** dùng như kiểu nào? | Giá trị/đối tượng **thực sự** là gì? |
| Nơi xử lý | **javac** (hoặc compiler Java khác) | JVM và thư viện runtime |
| Ví dụ | **pet** có kiểu Animal | Đối tượng trong pet thuộc lớp Dog |
| Quyết định điển hình | Kiểm tra phép gán, truy cập member, chọn overload | Dispatch phương thức instance được override, kiểm tra cast, instanceof |
| Công cụ quan sát | Khai báo biến, chữ ký method, kiểu biểu thức | **getClass()**, **instanceof**, Reflection |

**Lưu ý về thuật ngữ:** Với primitive như **int**, kiểu tĩnh vẫn tồn tại nhưng không có đối tượng Java tương ứng để gọi **getClass()** trực tiếp. Cũng cần phân biệt “kiểu của biểu thức lúc biên dịch” với “lớp của một đối tượng lúc chạy”: chúng không phải hai phép đo luôn cùng loại.

## 3. Ví dụ chạy được: kiểu tĩnh, override và overload

Tạo tệp **TypeStagesDemo.java**:

~~~java
public class TypeStagesDemo {
    static class Animal {
        String voice() {
            return "animal";
        }
    }

    static class Dog extends Animal {
        @Override
        String voice() {
            return "woof";
        }

        void fetch() {
            System.out.println("fetch");
        }
    }

    static String describe(Animal value) {
        return "overload Animal";
    }

    static String describe(Dog value) {
        return "overload Dog";
    }

    public static void main(String[] args) {
        Animal pet = new Dog();

        System.out.println("Runtime class: " + pet.getClass().getSimpleName());
        System.out.println("Override: " + pet.voice());
        System.out.println("Overload: " + describe(pet));
        System.out.println("instanceof Dog: " + (pet instanceof Dog));
        System.out.println("Animal.class matches: " + Animal.class.equals(pet.getClass()));
        System.out.println("Dog.class matches: " + Dog.class.equals(pet.getClass()));

        if (pet instanceof Dog dog) {
            dog.fetch();
            System.out.println("Overload after narrowing: " + describe(dog));
        }
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac TypeStagesDemo.java
java TypeStagesDemo
~~~

Kết quả:

~~~text
Runtime class: Dog
Override: woof
Overload: overload Animal
instanceof Dog: true
Animal.class matches: false
Dog.class matches: true
fetch
Overload after narrowing: overload Dog
~~~

Giải thích từng điểm:

1. **pet.getClass().getSimpleName()** đọc lớp thực tế, nên là Dog.
2. **pet.voice()** biên dịch được vì Animal khai báo voice(). Khi chạy, JVM thực thi bản override của Dog.
3. **describe(pet)** chọn overload nhận Animal vì kiểu tĩnh của pet là Animal, dù đối tượng thực tế là Dog. Chọn overload chủ yếu là quyết định lúc biên dịch; **không** tự chọn lại bằng runtime class của argument.
4. **pet instanceof Dog** kiểm tra lớp thực tế của đối tượng; pattern variable **dog** có kiểu Dog trong nhánh phù hợp.
5. Sau kiểm tra **instanceof**, **describe(dog)** chọn overload nhận Dog vì kiểu tĩnh của biến mới là Dog.
6. **pet.fetch()** sẽ **không biên dịch**: Animal không khai báo fetch(). Muốn gọi cần một tham chiếu đã được thu hẹp an toàn hoặc thực hiện cast phù hợp.

Đừng nhầm khả năng gọi phương thức với việc lựa chọn phần triển khai: compiler quyết định một lời gọi có hợp lệ theo kiểu tĩnh không; với lời gọi phương thức instance có override, runtime quyết định phần triển khai nào nhận lời gọi.

## 4. Những phép kiểm tra diễn ra ở giai đoạn nào?

### 4.1. Phép gán và member access

~~~java
Animal a = new Dog();     // Hợp lệ: Dog là subtype của Animal
// Dog d = a;             // Lỗi biên dịch: Animal chưa chắc là Dog
Dog d = (Dog) a;          // Hợp lệ khi chạy vì a đang trỏ tới Dog
~~~

Compiler cho phép phép downcast **(Dog) a** vì về mặt quan hệ kiểu phép ép có khả năng thành công; JVM kiểm tra đối tượng lúc chạy. Nếu a trỏ tới một đối tượng Animal không phải Dog, phép ép gây **ClassCastException**. Ép kiểu tham chiếu không thay đổi runtime class của đối tượng.

### 4.2. instanceof và pattern matching

~~~java
Object value = "Java";
if (value instanceof String text) {
    System.out.println(text.length()); // 4
}
~~~

**instanceof** kiểm tra giá trị thực lúc chạy. Nếu giá trị là null, kết quả của kiểm tra kiểu là false. Pattern variable text chỉ có hiệu lực ở nhánh mà compiler chứng minh điều kiện khớp.

### 4.3. Overloading, overriding, field và static method

- **Overloading**: quyết định chữ ký phương thức từ các kiểu lúc biên dịch của argument và các quy tắc phân giải overload. Ví dụ **describe(pet)** chọn bản nhận Animal.
- **Overriding**: đối với phương thức instance có thể override, JVM lựa chọn triển khai dựa trên lớp thực tế của receiver. Ví dụ **pet.voice()** chạy Dog.voice().
- **Field hiding**: truy cập field qua biểu thức thường phụ thuộc kiểu tĩnh của biểu thức; field không có đa hình như instance method.
- **Static method hiding**: lời gọi qua kiểu/tham chiếu được phân giải theo các quy tắc tĩnh; static method không bị override. Tránh gọi static method qua instance vì dễ gây hiểu nhầm.

Một câu ghi nhớ hữu ích: **kiểu tĩnh giới hạn điều được phép gọi; đa hình quyết định bản override được chạy**.

## 5. Reflection nhìn thấy kiểu gì?

### 5.1. Class literal và getClass()

Có hai cách nhận đối tượng metadata **Class** với ý nghĩa khác nhau:

~~~java
Class<?> declared = Animal.class; // Biết lớp Animal từ source code
Animal pet = new Dog();
Class<?> actual = pet.getClass(); // Lớp Dog của đối tượng lúc chạy
~~~

- **Animal.class** là class literal cho Animal, không phụ thuộc giá trị hiện tại của biến.
- **pet.getClass()** là phương thức trên Object, lấy lớp thực tế của đối tượng và yêu cầu pet khác null.
- **Class<?>** biểu diễn metadata của một kiểu có Class token; dùng wildcard khi mã không biết tham số kiểu chính xác.
- **Class.forName("com.example.Dog")** có thể tìm lớp bằng tên đầy đủ khi chạy, thông qua cơ chế class loading; bản một tham số còn khởi tạo lớp nếu chưa được khởi tạo. Nó có thể ném ClassNotFoundException.
- Class token được định danh bởi **tên lớp cùng defining class loader**. Cùng tên nhị phân nhưng do hai class loader khác nhau định nghĩa có thể là hai kiểu runtime khác nhau.

**Không nên suy luận rằng getClass() có thể trả về “kiểu khai báo của biến”.** Đối tượng không mang thông tin riêng rằng nó từng được lưu vào biến Animal, Object hay một biến generic nào đó.

### 5.2. Kiểm tra quan hệ kiểu bằng Class

~~~java
Class<?> parent = Animal.class;
Class<?> child = Dog.class;

System.out.println(parent.isAssignableFrom(child)); // true
System.out.println(child.isAssignableFrom(parent)); // false

Animal pet = new Dog();
System.out.println(child.isInstance(pet));           // true
~~~

Ý nghĩa của **X.isAssignableFrom(Y)**: một giá trị có kiểu Y có thể được gán cho biến kiểu X theo quan hệ chuyển đổi kiểu tham chiếu phù hợp. Vì Dog extends Animal, **Animal.class.isAssignableFrom(Dog.class)** trả true, còn chiều ngược lại false. Với một đối tượng cụ thể, **Dog.class.isInstance(pet)** tương tự kiểm tra **pet instanceof Dog** tại runtime, và trả false khi pet là null.

Các API bổ sung:
- **targetClass.cast(object)**: kiểm tra và cast đối tượng theo Class token; có thể ném ClassCastException.
- **someClass.asSubclass(Base.class)**: xác thực quan hệ subclass trên Class token; có thể ném ClassCastException.
- **getSuperclass()**, **getInterfaces()**: xem quan hệ kế thừa/interface trực tiếp trong metadata.
- **getDeclaredMethods()**, **getDeclaredFields()**: xem member khai báo trực tiếp trong lớp; khác với **getMethods()** vốn xét các public method được kế thừa theo quy tắc API.

### 5.3. Ví dụ kiểm tra một member đã khai báo

Tạo tệp **ReflectionInspectDemo.java**:

~~~java
import java.lang.reflect.Method;

public class ReflectionInspectDemo {
    static class Base {
        public void start() {}
    }

    static class Worker extends Base {
        private void process() {}
    }

    public static void main(String[] args) throws Exception {
        Class<?> type = Worker.class;
        Method local = type.getDeclaredMethod("process");
        Method inherited = type.getMethod("start");

        System.out.println(type.getSimpleName());
        System.out.println(local.getDeclaringClass().getSimpleName());
        System.out.println(inherited.getDeclaringClass().getSimpleName());
        System.out.println(type.getSuperclass().getSimpleName());
    }
}
~~~

~~~bash
javac ReflectionInspectDemo.java
java ReflectionInspectDemo
~~~

Kết quả xác định:

~~~text
Worker
Worker
Base
Base
~~~

Ở đây **getDeclaredMethod("process")** tìm phương thức private khai báo trong Worker. **getMethod("start")** tìm public method được kế thừa từ Base. Việc *tìm metadata* không đồng nghĩa với quyền *truy cập hoặc gọi* member đó; phản chiếu vào private member còn chịu kiểm soát truy cập và giới hạn module của Java Platform Module System. Đừng mặc định **setAccessible(true)** sẽ thành công.

## 6. Generics: thông tin nào bị xóa, thông tin nào còn?

Java thường biên dịch generic bằng cơ chế **type erasure**. Kiểu tham số hóa như **List\<String>** giúp compiler kiểm tra an toàn kiểu khi viết code, nhưng đối tượng ArrayList lúc chạy không tự mang nhãn phần tử String.

Ví dụ biên dịch hợp lệ:

~~~java
import java.util.ArrayList;
import java.util.List;

List<String> names = new ArrayList<>();
List<Integer> numbers = new ArrayList<>();

System.out.println(names.getClass().equals(numbers.getClass())); // true
System.out.println(names.getClass().getName()); // java.util.ArrayList
~~~

**List\<String>** và **List\<Integer>** khác nhau ở tầng kiểm tra kiểu lúc biên dịch, nhưng hai đối tượng **new ArrayList<>()** có cùng runtime class **java.util.ArrayList**.

Các giới hạn cần nhớ:
- **List\<String>.class** không hợp lệ; class literal dùng được với **List.class** (raw type) hoặc một Class token thích hợp khác.
- Với biến `Object value`, `value instanceof List<String>` không hợp lệ vì phép kiểm tra cần một chuyển đổi không an toàn kiểu (unchecked). Từ Java 16, với biến `List<String> value`, `value instanceof List<String>` và `value instanceof ArrayList<String>` có thể hợp lệ vì kiểu tĩnh đã đủ thông tin để kiểm tra mà không cần chuyển đổi unchecked. `value instanceof List<?>` vẫn là cách kiểm tra phù hợp khi chỉ cần biết đối tượng có phải một danh sách; không kiểm tra kiểu từng phần tử tại runtime.
- **getClass()** của ArrayList không thể tự suy ra rằng một biến bên ngoài khai báo là List\<String>.
- Không có cam kết rằng một danh sách tại runtime luôn chứa phần tử thuộc kiểu đã ghi trong source: raw type, unchecked conversion hoặc Reflection có thể tạo ra heap pollution; compiler thường phát cảnh báo trong các tình huống như vậy.

**Nhưng “type erasure” không có nghĩa mọi dấu vết generic đều biến mất.** Metadata của *khai báo* field, method, superclass hoặc interface có thể giữ generic signature trong class file và đọc được qua **java.lang.reflect.Type** (ví dụ ParameterizedType, TypeVariable, WildcardType). Điều đó khác với việc mỗi instance có một đối tượng Class riêng cho từng type argument.

### Ví dụ getType() so với getGenericType()

Tạo tệp **GenericMetadataDemo.java**:

~~~java
import java.lang.reflect.Field;
import java.util.List;

public class GenericMetadataDemo {
    private List<String> labels;

    public static void main(String[] args) throws Exception {
        Field field = GenericMetadataDemo.class.getDeclaredField("labels");

        System.out.println(field.getType().getTypeName());
        System.out.println(field.getGenericType().getTypeName());
    }
}
~~~

~~~bash
javac GenericMetadataDemo.java
java GenericMetadataDemo
~~~

Kết quả:

~~~text
java.util.List
java.util.List<java.lang.String>
~~~

**getType()** trả về Class cho kiểu đã erasure của field. **getGenericType()** đọc kiểu khai báo trong generic signature khi metadata có sẵn. Nếu khai báo dùng type variable **T**, Reflection có thể trả về **TypeVariable**; muốn tìm đối số kiểu cụ thể trong một hệ phân cấp generic, thường phải phân tích tiếp cấu trúc Type, và có trường hợp không thể khôi phục kiểu mà caller từng dùng.

## 7. Mảng và primitive: hai ngoại lệ dễ nhầm

### 7.1. Runtime component type của mảng

Mảng là đối tượng có runtime component type. Vì mảng tham chiếu trong Java có tính **covariant**, phép gán sau đây hợp lệ lúc biên dịch nhưng thao tác ghi bị kiểm tra lúc chạy:

Tạo tệp **ArrayRuntimeTypeDemo.java**:

~~~java
public class ArrayRuntimeTypeDemo {
    public static void main(String[] args) {
        Object[] items = new String[1];

        System.out.println(items.getClass().getComponentType().getName());

        try {
            items[0] = 42;
        } catch (ArrayStoreException ex) {
            System.out.println("ArrayStoreException");
        }
    }
}
~~~

~~~bash
javac ArrayRuntimeTypeDemo.java
java ArrayRuntimeTypeDemo
~~~

Kết quả:

~~~text
java.lang.String
ArrayStoreException
~~~

Biến items có kiểu tĩnh **Object[]**, nhưng đối tượng thực tế là **String[]**. JVM không cho lưu Integer vào mảng String, nên ném **ArrayStoreException**. Điều này khác với danh sách generic đã erasure: JVM thực sự biết runtime component type của mảng.

### 7.2. Primitive và wrapper

~~~java
Class<?> primitive = int.class;
Class<?> wrapper = Integer.class;

System.out.println(primitive.isPrimitive()); // true
System.out.println(wrapper.isPrimitive());   // false
System.out.println(primitive.equals(Integer.TYPE)); // true
~~~

**int.class** đại diện metadata cho primitive int, nhưng một giá trị **int** không phải đối tượng và không có phương thức **getClass()**. Khi gán int cho Object, Java thực hiện boxing thành Integer; nếu sau đó gọi getClass() trên đối tượng boxed, ta nhận **Integer.class**, không phải **int.class**. Đừng trộn lẫn primitive và wrapper khi tìm constructor hoặc method bằng signature Reflection.

## 8. Phân biệt khả năng kiểm tra và khả năng truy vấn

| Câu hỏi thực tế | Dùng gì? | Cần cảnh giác |
| --- | --- | --- |
| Biến được phép gọi member nào? | Kiểu khai báo và luật compiler | Đối tượng có thể thuộc subclass giàu member hơn |
| Đối tượng khác null hiện thuộc lớp nào? | **obj.getClass()** | Không trả kiểu khai báo biến |
| Giá trị có tương thích với một subtype? | **instanceof**, **Class.isInstance()** | null không khớp |
| Class A có nhận giá trị kiểu B? | **A.isAssignableFrom(B)** | Dễ đảo chiều |
| Lấy Class token khi đã biết kiểu trong source? | **SomeType.class** | Không phản ánh đối tượng hiện tại |
| Tìm chữ ký field generic? | **Field.getGenericType()** | Metadata thuộc khai báo; không chứng minh phần tử instance |
| Tìm runtime component type của mảng? | **array.getClass().getComponentType()** | Mảng primitive và mảng tham chiếu khác nhau |
| Tìm method khi chạy? | **getMethod/getDeclaredMethod** | Khác nhau về inherited/public; truy cập còn bị kiểm soát |

### Gợi ý khi viết API dùng Reflection

Nếu logic biết trước kiểu và hành vi cần gọi, ưu tiên interface, generic và đa hình bình thường: compiler sẽ kiểm tra giúp bạn. Reflection phù hợp hơn với việc phải khảo sát schema/metadata hoặc framework cần khám phá class, field, method lúc chạy. Khi dùng Reflection:

1. Xác định bạn đang xử lý **Class**, **Type**, một **Field/Method** khai báo, hay một **instance** cụ thể.
2. Phân biệt câu hỏi về **quan hệ assignable** với câu hỏi **lớp thực tế có đúng bằng lớp X không**. **Animal.class.equals(pet.getClass())** có thể false nhưng **pet instanceof Animal** vẫn true.
3. Chú ý **class loader**, **null**, **erasure**, **access control** và checked exceptions khi tra cứu bằng tên.
4. Không dựa vào thứ tự kết quả của **getDeclaredMethods()**/**getDeclaredFields()**: API không cam kết một thứ tự cố định.
5. Kiểm tra chữ ký parameter chính xác khi dùng **getMethod(name, parameterTypes...)**; generic argument trong source thường đã erasure.

## 9. Các hiểu lầm thường gặp

**“Biến Animal trỏ tới Dog thì compiler cho gọi mọi method Dog.”** Sai. Compiler kiểm tra theo kiểu tĩnh của biến; dùng đa hình qua method đã khai báo ở Animal, hoặc thu hẹp có kiểm tra nếu thực sự cần member của Dog.

**“Override và overload đều chọn theo runtime class.”** Sai. Overload lựa chọn chữ ký lúc biên dịch; override dispatch theo receiver lúc chạy.

**“Ép kiểu đối tượng sang Animal biến đối tượng thành Animal.”** Sai. Cast đổi cách biểu thức được xét kiểu; đối tượng Dog vẫn có runtime class Dog nếu cast hợp lệ.

**“Reflection luôn khôi phục List\<String> của một ArrayList instance.”** Sai. Generic signature của khai báo đôi khi đọc được, nhưng đó không phải nhãn type argument có trên mọi đối tượng.

**“Class.getName() trùng thì hai Class token chắc chắn cùng kiểu.”** Sai trong tình huống nhiều defining class loader.

**“getDeclaredMethods() trả toàn bộ public method kể cả kế thừa.”** Sai; cần hiểu khác biệt declared so với public/inherited.

## 10. Tự kiểm tra

Cho khai báo **Animal a = new Dog()** với Dog extends Animal, Dog override voice() và bổ sung fetch():

1. Kiểu tĩnh của a là gì? Runtime class là gì?
2. Vì sao **a.voice()** chạy bản Dog nhưng **a.fetch()** không biên dịch?
3. Hai overload **f(Animal)** và **f(Dog)** thì **f(a)** gọi bản nào?
4. **Animal.class.isAssignableFrom(Dog.class)** trả gì? **Dog.class.isAssignableFrom(Animal.class)** trả gì?
5. Nếu **List\<String>** và **List\<Integer>** cùng được tạo bằng ArrayList, getClass() có phân biệt type argument không?
6. Vì sao phép gán **Object[] values = new String[1]** hợp lệ nhưng ghi Integer vào values có thể ném lỗi?

Đáp án: (1) Animal và Dog. (2) Compiler thấy voice ở Animal và JVM dispatch override; fetch không thuộc API của kiểu tĩnh Animal. (3) f(Animal). (4) true rồi false. (5) Không, vì erasure và cùng lớp ArrayList. (6) Mảng covariant nhưng JVM kiểm tra runtime component type, nên ArrayStoreException.

## 11. Tổng kết

Trong Java, **thông tin kiểu lúc biên dịch** dùng để chứng minh code hợp lệ và xác định nhiều lựa chọn tĩnh; **thông tin kiểu lúc chạy** mô tả giá trị/đối tượng thật và phục vụ dispatch đa hình, kiểm tra kiểu động và Reflection. **Class<?>** cung cấp metadata về lớp runtime hoặc kiểu được nêu trực tiếp, còn **Type** biểu diễn thêm một số khai báo generic. Nắm rõ ranh giới này giúp bạn dự đoán lỗi biên dịch, ClassCastException, ArrayStoreException và giới hạn của các thư viện dựa trên Reflection.
