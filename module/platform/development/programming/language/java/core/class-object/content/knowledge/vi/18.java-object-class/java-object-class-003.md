# Phân biệt class, đối tượng thông thường và đối tượng `Class` trong Java

Java có ba khái niệm liên quan nhưng **không đồng nhất**:

1. **Class (lớp)** là định nghĩa kiểu trong source code, chẳng hạn `class Student { ... }`. Class mô tả constructors, instance fields, methods và những quy tắc cho các thể hiện của nó.
2. **Ordinary object (đối tượng thông thường / instance)** là một thực thể ở runtime, chẳng hạn object được tạo bởi `new Student("Mai")`. Nó có identity và có thể có instance state.
3. **`java.lang.Class<?>` object** là **đối tượng metadata về runtime type**. `Student.class` trả một Class object đại diện kiểu Student; nó **không phải** một Student instance.

~~~java
class Student {
    String name;
}

// Trong một method:
Student student = new Student();      // Student instance.
Class<Student> type = Student.class;   // Class object mô tả Student.
Class<?> runtime = student.getClass(); // Class object của actual runtime class.
~~~

`Student.class` không gọi constructor, không tạo Student instance và không phải tệp bytecode trên ổ đĩa. Class object cho phép JVM/framework/caller hỏi **kiểu này tên gì, kế thừa ai, khai báo member nào**, còn Student instance là đối tượng có field `name` cụ thể.

Bài viết thuộc **Java Core — Class & Object / Lớp Object**, sử dụng **Java 17+**. Các chương trình độc lập ghi tên file, lệnh `javac`/`java` và stdout. Các đoạn mã lẻ là minh họa, không nhất thiết chạy độc lập.

## 1. Mục tiêu học tập

Bạn sẽ có thể:

- Phân biệt class declaration, instance và metadata Class object.
- Phân biệt keyword `class`, class API `Class` và class literal `.class`.
- Hiểu vai trò của `java.lang.Object` và quan hệ `Class extends Object`.
- Đọc `getClass()` dựa theo actual runtime object thay vì declared reference type.
- Biết tại sao nhiều instances cùng runtime class dùng chung một Class object trong cùng defining-loader scope.
- Phân biệt `Object.class`, `Class.class`, `String.class` và String instance.
- Dùng đúng `Class<T>`, `Class<?>`, `isInstance`, `isAssignableFrom`, `cast`.
- Biết Class tokens cho primitives, `void`, arrays, interfaces, records và enums.
- Hiểu khi nào `Class.forName` kích hoạt initialization còn `.class` không.
- Tách metadata Field/Method/Constructor khỏi giá trị instance state.
- Biết Reflection APIs và giới hạn access, type erasure, class-loader identity.
- Dự đoán chính xác code Java và tránh nhầm lẫn khi dùng reflection.

## 2. Mô hình ba tầng

Giả sử:

~~~java
class Person {
    String name;
}

Person mai = new Person();
Person an = new Person();

Class<Person> type = Person.class;
~~~

Mô hình:

~~~text
KHAI BÁO KIỂU (source)
     class Person { String name; }
                  |
                  v
RUNTIME METADATA CHO KIỂU PERSON
     một Class object: Person.class
                  ^
                  |
          getClass() từ các instances
                  |
     +------------+-------------+
     |                          |
 Person object #1           Person object #2
 (mai, name riêng)          (an, name riêng)
~~~

Có thể tồn tại hai Person instances mà cùng một runtime Class object. Ngược lại, **Class object không chứa một danh sách mặc định của tất cả Person instances**. Java không có API `Person.class.getAllInstances()`.

### Điều gì được chia sẻ?

- Class metadata: mô tả runtime type được chia sẻ.
- Instance fields: mỗi ordinary instance có trạng thái riêng theo constructor/class design.
- Static fields: dữ liệu gắn với runtime class, không phải bản sao cho mỗi ordinary object.
- Class object identity: gắn với chính runtime type, có xét defining class loader.

Class metadata khác với “storage container chứa mọi giá trị instance fields”.

## 3. `class`, `Class`, `.class` khác nhau

| Biểu thức hoặc khai báo | Ý nghĩa |
| --- | --- |
| `class Book {}` | Java keyword khai báo class |
| `java.lang.Class` | API class đại diện runtime types |
| `Class<Book>` | Reference type đến Class object mô tả Book |
| `Book.class` | Class literal expression |
| `new Book()` | Tạo ordinary Book object |
| `book.getClass()` | Lấy actual runtime Class object của book |
| `Class.forName("pkg.Book")` | Tìm/load runtime class qua binary name |
| `Object.class` | Class object mô tả Object type |

Java phân biệt chữ hoa. `Class` là tên class thư viện, không phải keyword. `Book.class` không phải một method tên class được gọi trên Book.

### File `.class` khác class literal

- `Book.java`: file nguồn.
- `Book.class` trên filesystem: file bytecode.
- `Book.class` **trong Java expression**: giá trị Class object.

Dù chữ viết giống nhau, class literal không mở file bytecode mỗi lần được đánh giá. Runtime class có thể được custom loader định nghĩa từ bytes không nằm trong một file truyền thống.

## 4. `Object` là superclass gốc, `Class` cũng là Object

`java.lang.Object` là superclass gốc của các class thông thường. `java.lang.Class` là một class thực sự, kế thừa Object.

Do đó:

~~~java
Object value = String.class;
System.out.println(value.getClass() == Class.class);
~~~

in `true`.

Nhưng:

~~~java
Object value = "Java";
System.out.println(value.getClass() == String.class);
~~~

cũng true, vì ở đây `value` là một **String instance**.

Hai đối tượng ở hai cấp:

~~~text
"Java"          --> ordinary String object
String.class    --> Class object mô tả String
Class.class     --> Class object mô tả chính java.lang.Class
~~~

Đặc biệt: `Class.class.getClass() == Class.class` là true. Không có chuỗi vô hạn “Class của Class của Class”.

## 5. Ví dụ chạy: ordinary objects và Class object

Tạo **`ThreeLevelsDemo.java`**:

~~~java
public class ThreeLevelsDemo {
    static final class Student {
        private final String name;

        Student(String name) {
            this.name = name;
        }

        String name() {
            return name;
        }
    }

    public static void main(String[] args) {
        Student mai = new Student("Mai");
        Student an = new Student("An");

        Class<Student> type = Student.class;
        Class<?> fromMai = mai.getClass();
        Class<?> fromAn = an.getClass();

        System.out.println("mai=" + mai.name());
        System.out.println("an=" + an.name());
        System.out.println("same instance=" + (mai == an));
        System.out.println("same Class=" + (fromMai == fromAn));
        System.out.println("literal matches=" + (type == fromMai));
        System.out.println("type=" + type.getSimpleName());
        System.out.println("Class itself=" +
                (type.getClass() == Class.class));
    }
}
~~~

~~~bash
javac -encoding UTF-8 ThreeLevelsDemo.java
java ThreeLevelsDemo
~~~

Stdout:

~~~text
mai=Mai
an=An
same instance=false
same Class=true
literal matches=true
type=Student
Class itself=true
~~~

Hai lần `new Student(...)` tạo hai objects; cùng runtime type Student khiến hai `getClass()` trả cùng Class token. `Student.class` cũng cho chính token đó. Nhưng `type.getClass()` lấy runtime class của **metadata object**, là `java.lang.Class`.

## 6. `Object.class` và `Class.class` hỏi hai kiểu khác nhau

`Object.class` đại diện cho **runtime type Object**, không “chứa mọi object”.

`Class.class` đại diện cho **runtime type Class**. Chính nó cũng là một Class instance.

Tạo **`ObjectAndClassDemo.java`**:

~~~java
public class ObjectAndClassDemo {
    public static void main(String[] args) {
        Object ordinary = "Java";
        Object metadata = String.class;

        System.out.println("ordinary type=" +
                ordinary.getClass().getSimpleName());
        System.out.println("metadata type=" +
                metadata.getClass().getSimpleName());
        System.out.println("String type=" +
                String.class.getSimpleName());
        System.out.println("Class type=" +
                Class.class.getSimpleName());

        System.out.println("Class parent is Object=" +
                (Class.class.getSuperclass() == Object.class));
        System.out.println("Object parent null=" +
                (Object.class.getSuperclass() == null));
        System.out.println("Class self=" +
                (Class.class.getClass() == Class.class));
    }
}
~~~

~~~bash
javac -encoding UTF-8 ObjectAndClassDemo.java
java ObjectAndClassDemo
~~~

Stdout:

~~~text
ordinary type=String
metadata type=Class
String type=String
Class type=Class
Class parent is Object=true
Object parent null=true
Class self=true
~~~

Một Class token cũng là Object vì Class extends Object; không thể vì token mô tả String mà nói token là String instance.

## 7. `getClass()` trả metadata của *object hiện có*, không trả kiểu của biến

Với `Animal animal = new Dog();` (giả sử `Dog extends Animal`), `animal.getClass()` trả `Dog.class`: nó không trả `Animal.class` chỉ vì biến có kiểu Animal. `getClass()` là final nên class con không thể override để giả metadata khác.

Hai phép kiểm tra khác nhau:

- `object.getClass() == Animal.class` — đúng khi runtime class **chính xác** là Animal; null receiver gây NPE.
- `object instanceof Animal` — chấp nhận subclass và trả false với null.

Đây là nền tảng để đọc `Class` object. Bài chuyên sâu `getClass()` tập trung static-vs-runtime type; bài này sẽ chuyển trọng tâm sang **đối tượng metadata `Class` có identity khác ordinary instances** và cách khai thác nó.

## 8. Chương trình hoàn chỉnh: hai instances nhưng một Class token

Lưu file **`ClassTokenAndInstancesDemo.java`**:

~~~java
public class ClassTokenAndInstancesDemo {
    static final class Student {
        private final String name;

        Student(String name) {
            this.name = name;
        }
    }

    public static void main(String[] args) {
        Student first = new Student("Lan");
        Student second = new Student("Mai");
        Class<?> type = first.getClass();

        System.out.println("same instances=" + (first == second));
        System.out.println("same metadata=" + (type == second.getClass()));
        System.out.println("literal matches=" + (type == Student.class));
        System.out.println("first is Student=" + type.isInstance(first));
        System.out.println("token is Student=" + type.isInstance(type));
        System.out.println("token class=" + type.getClass().getSimpleName());
    }
}
~~~

~~~bash
javac -encoding UTF-8 ClassTokenAndInstancesDemo.java
java ClassTokenAndInstancesDemo
~~~

**Stdout:**

~~~text
same instances=false
same metadata=true
literal matches=true
first is Student=true
token is Student=false
token class=Class
~~~

Hai lần `new Student(...)` tạo **hai ordinary objects** có identity khác nhau; cả hai trả cùng `Class` token cho Student trong cùng runtime definition. `type` bản thân là một object của class `java.lang.Class`, **không phải Student instance**. `Class.isInstance(obj)` hỏi một object có thuộc kiểu được token mô tả hay không, chứ không hỏi token có chứa fields của Student.

## 9. Class token không phải instance của kiểu được mô tả

Nếu:

~~~java
Class<String> type = String.class;
Object ordinary = "hello";
~~~

thì `type` là Class instance, **không phải String instance**.

Tạo **`ClassTokenNotValueDemo.java`**:

~~~java
public class ClassTokenNotValueDemo {
    public static void main(String[] args) {
        Class<String> type = String.class;
        Object ordinary = "hello";

        System.out.println("token is Class=" +
                (type instanceof Class));
        System.out.println("token is Object=" +
                (type instanceof Object));
        System.out.println("ordinary is String=" +
                type.isInstance(ordinary));
        System.out.println("token is String=" +
                type.isInstance(type));
        System.out.println("token is Class=" +
                Class.class.isInstance(type));
    }
}
~~~

~~~bash
javac -encoding UTF-8 ClassTokenNotValueDemo.java
java ClassTokenNotValueDemo
~~~

Stdout:

~~~text
token is Class=true
token is Object=true
ordinary is String=true
token is String=false
token is Class=true
~~~

`String.class.isInstance(type)` false vì chính type token không phải String. `Class.class.isInstance(type)` true vì token là Class object.

## 10. Ba cách lấy Class object

| Cú pháp | Khi dùng | Có ordinary instance? |
| --- | --- | --- |
| `SomeType.class` | Biết type ở compile time | Không cần |
| `object.getClass()` | Cần actual runtime class | Cần non-null object |
| `Class.forName(name)` | Tên runtime type đến từ configuration/plugin | Không cần instance trực tiếp |

Nếu tất cả cùng nhắm một runtime class identity, chúng có thể trả **cùng Class object**. Nhưng initialization semantics khác nhau:

- Class literal **không tự yêu cầu** khởi tạo class được mô tả.
- `getClass()` được gọi trên object đã tồn tại.
- `Class.forName(String)` có thể gây class initialization.
- Overload `Class.forName(name, false, loader)` không yêu cầu initialize class.

Không thay một cách bằng cách khác khi class initialization side effects là điều quan trọng.

## 11. Generic `Class<T>` và wildcard `Class<?>`

`java.lang.Class` là generic class. Ví dụ:

~~~java
Class<String> textType = String.class;
Class<Integer> numberType = Integer.class;
Class<?> unknownType = new java.util.ArrayList<>().getClass();
~~~

`Class<String>` nói token đại diện String type. `Class<?>` nói token của một type chưa xác định cụ thể ở compile time.

### API dùng Class token

~~~java
static <T> T convert(Class<T> target, Object input) {
    return target.cast(input);
}
~~~

Khi caller truyền `String.class`, compiler biết return type T là String. Không nên dùng raw `Class` nếu `Class<?>` hoặc `Class<T>` thể hiện ý định rõ hơn.

### Giới hạn

Class<T> không biểu diễn mọi parameterized generic types: không có `List<String>.class` literal. Khi framework cần generic type declarations có thể dùng `java.lang.reflect.Type` và related APIs, nhưng ordinary object `getClass()` không tự tiết lộ mọi type arguments do erasure.

## 12. `Class.isInstance`, `Class.cast` và `isAssignableFrom`

**`SomeType.class.isInstance(object)`** kiểm tra object có thể xem như instance của SomeType hay không.

**`SomeType.class.cast(object)`** thực hiện runtime checked cast, có thể ném `ClassCastException`. `cast(null)` trả null; `isInstance(null)` false.

**`A.class.isAssignableFrom(B.class)`** hỏi: giá trị kiểu B có thể gán cho biến kiểu A không? A là **target/đích**, B là source.

Nếu Dog extends Animal:

~~~java
Animal.class.isAssignableFrom(Dog.class) // true.
Dog.class.isAssignableFrom(Animal.class) // false.
Object.class.isAssignableFrom(Dog.class) // true.
~~~

### Ví dụ chạy

Tạo **`ClassChecksDemo.java`**:

~~~java
public class ClassChecksDemo {
    static class Animal {}
    static final class Dog extends Animal {}

    static <T> T checked(Class<T> expected, Object value) {
        if (!expected.isInstance(value)) {
            throw new IllegalArgumentException(
                    "expected " + expected.getSimpleName());
        }
        return expected.cast(value);
    }

    public static void main(String[] args) {
        Animal animal = new Dog();

        System.out.println("Animal <- Dog=" +
                Animal.class.isAssignableFrom(Dog.class));
        System.out.println("Dog <- Animal=" +
                Dog.class.isAssignableFrom(Animal.class));
        System.out.println("Dog instance=" +
                Dog.class.isInstance(animal));

        Dog dog = checked(Dog.class, animal);
        System.out.println("cast type=" +
                dog.getClass().getSimpleName());

        try {
            checked(String.class, animal);
        } catch (IllegalArgumentException ex) {
            System.out.println("rejected=" + ex.getMessage());
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 ClassChecksDemo.java
java ClassChecksDemo
~~~

Stdout:

~~~text
Animal <- Dog=true
Dog <- Animal=false
Dog instance=true
cast type=Dog
rejected=expected String
~~~

`isAssignableFrom` so sánh hai runtime type tokens; `isInstance` hỏi về một object; `cast` tạo một reference typed phù hợp, **không tạo object mới**.

## 13. Primitive types có Class tokens, không là Object instances

Java có tám primitive types: `boolean`, `byte`, `short`, `char`, `int`, `long`, `float` và `double`. Primitive values không phải ordinary objects, nhưng đều có Class tokens:

~~~java
Class<?> a = int.class;
Class<?> b = boolean.class;
Class<?> c = void.class;
~~~

`void.class` cũng là Class token đặc biệt. `Class.isPrimitive()` trả true cho primitives và void theo API.

### Wrapper classes không cùng type với primitives

~~~java
int.class == Integer.class // false.
boolean.class == Boolean.class // false.
~~~

Autoboxing cho phép `int` value được chuyển sang Integer object trong một số contexts, nhưng không làm hai Class objects giống nhau.

~~~java
int number = 7;
// number.getClass(); // Lỗi: primitive không có instance method.
Object boxed = number;
System.out.println(boxed.getClass() == Integer.class); // true.
~~~

## 14. Arrays cũng có Class metadata

~~~java
int[] numbers = {1, 2};
String[][] matrix = new String[2][3];
~~~

Arrays là objects và có runtime Class tokens:

~~~java
numbers.getClass() == int[].class
matrix.getClass() == String[][].class
~~~

Các methods:

- `int[].class.isArray()` → true.
- `int[].class.getComponentType() == int.class` → true.
- `String[][].class.getComponentType() == String[].class` → true.
- `int[].class.getSuperclass() == Object.class` → true.

Array classes implement Cloneable và Serializable theo Java semantics. Không cần người dùng khai báo class tên `int[]` bằng Java syntax.

## 15. Interface cũng có Class token

~~~java
interface Action {
    void run();
}
~~~

`Action.class.isInterface()` true. Nhưng không thể `new Action()` trực tiếp. Một implementing class hoặc một lambda (khi Action là functional interface) tạo object mà `Action.class.isInstance(instance)` có thể true.

**`Action.class` bản thân nó không phải Action instance**; nó là Class instance đại diện Action type.

Đối với interface Class tokens, `getSuperclass()` trả null. Việc objects implementing interfaces là Objects không khiến interface có direct superclass Object theo `getSuperclass` API.

## 16. Ví dụ chạy: primitive, array, interface

Tạo **`SpecialTypesDemo.java`**:

~~~java
public class SpecialTypesDemo {
    interface Action {
        void run();
    }

    public static void main(String[] args) {
        Object boxed = 7;
        int[] values = {1, 2};
        Action action = () -> {};

        System.out.println("int primitive=" + int.class.isPrimitive());
        System.out.println("void primitive=" + void.class.isPrimitive());
        System.out.println("int != Integer=" + (int.class != Integer.class));
        System.out.println("boxed Integer=" +
                (boxed.getClass() == Integer.class));
        System.out.println("int[] array=" + int[].class.isArray());
        System.out.println("array token=" +
                (values.getClass() == int[].class));
        System.out.println("component int=" +
                (int[].class.getComponentType() == int.class));
        System.out.println("matrix component=" +
                (String[][].class.getComponentType() == String[].class));
        System.out.println("Action interface=" +
                Action.class.isInterface());
        System.out.println("Action instance=" +
                Action.class.isInstance(action));
    }
}
~~~

~~~bash
javac -encoding UTF-8 SpecialTypesDemo.java
java SpecialTypesDemo
~~~

Stdout:

~~~text
int primitive=true
void primitive=true
int != Integer=true
boxed Integer=true
int[] array=true
array token=true
component int=true
matrix component=true
Action interface=true
Action instance=true
~~~

Đừng hardcode tên runtime class của lambda object: đó có thể là tên generated khác theo implementation, còn interface-compatibility check là ngữ nghĩa cần học.

## 17. `getSuperclass()` và `getInterfaces()`

`Class.getSuperclass()` trả direct superclass (hoặc null theo API cho Object, interfaces, primitives/void). `getInterfaces()` trả Class tokens cho những interfaces trực tiếp được class/interface khai báo theo contract.

Ví dụ:

~~~java
interface Named {
    String name();
}

class Animal {}

class Dog extends Animal implements Named {
    public String name() {
        return "Dog";
    }
}
~~~

`Dog.class.getSuperclass() == Animal.class` true. `Animal.class.getSuperclass() == Object.class` true. `Object.class.getSuperclass() == null` true.

### Ví dụ chạy

Tạo **`HierarchyMetadataDemo.java`**:

~~~java
public class HierarchyMetadataDemo {
    interface Named {
        String name();
    }

    static class Animal {}

    static final class Dog extends Animal implements Named {
        @Override
        public String name() {
            return "Dog";
        }
    }

    public static void main(String[] args) {
        System.out.println("Dog parent=" +
                Dog.class.getSuperclass().getSimpleName());
        System.out.println("Animal parent=" +
                Animal.class.getSuperclass().getSimpleName());
        System.out.println("Object parent=" +
                Object.class.getSuperclass());
        System.out.println("Named parent=" +
                Named.class.getSuperclass());
        System.out.println("Dog direct interfaces=" +
                Dog.class.getInterfaces().length);
    }
}
~~~

~~~bash
javac -encoding UTF-8 HierarchyMetadataDemo.java
java HierarchyMetadataDemo
~~~

Stdout:

~~~text
Dog parent=Animal
Animal parent=Object
Object parent=null
Named parent=null
Dog direct interfaces=1
~~~

Không coi `getSuperclass()` là “mọi ancestors” hoặc `getInterfaces()` là “toàn bộ interfaces gián tiếp” theo một danh sách phẳng.

## 18. Class metadata là thông tin về declarations

`Class<?>` chứa/cho truy cập **mô tả type**, ví dụ:

- Tên, package, superclass/interfaces.
- Modifiers và annotations (tùy retention).
- Fields khai báo, types của fields.
- Methods khai báo, parameter/return types.
- Constructors, record components, sealed status.

Nhưng Class object **không chứa trực tiếp giá trị riêng của từng instance field**. Ví dụ Person #1 có name Mai và Person #2 có name An; Person.class vẫn là một token mô tả field `name`, không phải một name duy nhất.

### Phân biệt reflection Field và giá trị field

~~~java
java.lang.reflect.Field f =
        Person.class.getDeclaredField("name");
~~~

`f` là metadata descriptor về khai báo name. Muốn đọc `f.get(person)` cần ordinary instance target tương thích, quyền truy cập phù hợp và error handling. Private fields không tự được phép đọc chỉ vì tìm được metadata.

## 19. Các API reflection thường dùng

| API | Trả về thông tin gì? |
| --- | --- |
| `getDeclaredFields()` | Fields khai báo trực tiếp, gồm non-public |
| `getFields()` | Public fields phù hợp, có inherited public |
| `getDeclaredMethods()` | Methods khai báo trực tiếp, gồm non-public |
| `getMethods()` | Public methods phù hợp, có inherited methods |
| `getDeclaredConstructors()` | Constructors khai báo trực tiếp |
| `getConstructor(...)` | Tìm public constructor theo parameter types |
| `getDeclaredConstructor(...)` | Tìm declared constructor |
| `getModifiers()` | Modifier flags đọc qua Modifier API |
| `getName()` | Binary/runtime name |
| `getSimpleName()` | Simple name, có thể rỗng |
| `getCanonicalName()` | Canonical name, có thể null |
| `getTypeName()` | Tên kiểu để hiển thị, hữu ích cho arrays |
| `isInterface()/isArray()/isPrimitive()` | Kiểm tra loại type |
| `isEnum()/isRecord()/isSealed()` | Runtime type properties (Java 17) |

**Lưu ý:** API `getDeclared...` khác `get...` chủ yếu về phạm vi trực tiếp, inherited và visibility. Không suy luận rằng chỉ cần gọi `getDeclaredField` là có quyền phá private state.

## 20. Ví dụ chạy: Class metadata vs Field value

Tạo **`ReflectionMetadataDemo.java`**:

~~~java
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;

public class ReflectionMetadataDemo {
    public static final class User {
        private final String name;

        public User(String name) {
            this.name = name;
        }

        public String name() {
            return name;
        }
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        Class<User> type = User.class;

        Field field = type.getDeclaredField("name");
        Method method = type.getMethod("name");

        System.out.println("class=" + type.getSimpleName());
        System.out.println("field=" + field.getName());
        System.out.println("field type=" +
                field.getType().getSimpleName());
        System.out.println("field private=" +
                Modifier.isPrivate(field.getModifiers()));
        System.out.println("method return=" +
                method.getReturnType().getSimpleName());
        System.out.println("constructor count=" +
                type.getDeclaredConstructors().length);
    }
}
~~~

~~~bash
javac -encoding UTF-8 ReflectionMetadataDemo.java
java ReflectionMetadataDemo
~~~

Stdout:

~~~text
class=User
field=name
field type=String
field private=true
method return=String
constructor count=1
~~~

Chương trình **không tạo User ordinary instance nào**; nó chỉ xem declarations qua Class object. Đây là bằng chứng Class metadata không đồng nghĩa state của object.

## 21. Ví dụ chạy: một Field declaration, hai instance values

Tạo **`ReflectionValuesDemo.java`**:

~~~java
import java.lang.reflect.Field;

public class ReflectionValuesDemo {
    public static final class Meter {
        public int count = 5;
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        Meter first = new Meter();
        Meter second = new Meter();
        second.count = 9;

        Field descriptor = Meter.class.getField("count");

        System.out.println("field=" + descriptor.getName());
        System.out.println("first=" + descriptor.getInt(first));
        System.out.println("second=" + descriptor.getInt(second));
        System.out.println("same Class=" +
                (first.getClass() == second.getClass()));
    }
}
~~~

~~~bash
javac -encoding UTF-8 ReflectionValuesDemo.java
java ReflectionValuesDemo
~~~

Stdout:

~~~text
field=count
first=5
second=9
same Class=true
~~~

Cùng descriptor `count` nhưng giá trị nằm trên từng Meter object. Dùng public field ở đây cho reflection dễ minh họa; production classes thường đóng gói state trong private fields và methods có nghĩa.

## 22. Class token không phải constructor, nhưng dùng để tìm constructor

`Person.class` không tạo Person instance. Tạo instance bình thường:

~~~java
Person person = new Person("Mai");
~~~

Nếu cần reflection:

~~~java
Person person = Person.class
        .getConstructor(String.class)
        .newInstance("Mai");
~~~

Điều này cần public constructor(String) phù hợp, và phải xử lý reflection exceptions. `Class.newInstance()` đã deprecated; ưu tiên Constructor API hoặc typed constructor/factory.

### Ví dụ chạy

Tạo **`ReflectiveConstructorDemo.java`**:

~~~java
public class ReflectiveConstructorDemo {
    public static final class Person {
        private final String name;

        public Person(String name) {
            this.name = name;
        }

        public String name() {
            return name;
        }
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        Class<Person> token = Person.class;

        Person first = new Person("Mai");
        Person second = token.getConstructor(String.class)
                .newInstance("An");

        System.out.println("first=" + first.name());
        System.out.println("second=" + second.name());
        System.out.println("same instance=" + (first == second));
        System.out.println("same type=" +
                (first.getClass() == second.getClass()));
        System.out.println("token matches=" +
                (token == second.getClass()));
    }
}
~~~

~~~bash
javac -encoding UTF-8 ReflectiveConstructorDemo.java
java ReflectiveConstructorDemo
~~~

Stdout:

~~~text
first=Mai
second=An
same instance=false
same type=true
token matches=true
~~~

Tạo object qua reflection hay constructor trực tiếp đều cho ordinary Person instances; Class token vẫn chỉ đại diện runtime Person type.

## 23. Class loading và class initialization khác lấy Class token

Những khái niệm:

1. **Loading/definition:** JVM định nghĩa representation cho runtime type từ bytecode.
2. **Linking:** Verification, preparation và resolution theo quy tắc VM.
3. **Initialization:** Java thực thi static field initializers và static initializer blocks theo các quy tắc.
4. **Ordinary instance creation:** Constructor và instance initialization khi tạo object.

`SomeType.class` lấy Class token mà **không tự buộc initialization của SomeType**.

`Class.forName(String)` thường yêu cầu initialize class theo semantics API. Overload `Class.forName(name, false, loader)` cho phép không initialize ngay.

### Ví dụ chạy

Tạo **`ClassInitializationDemo.java`**:

~~~java
public class ClassInitializationDemo {
    static final class Plugin {
        static int version = 17;

        static {
            System.out.println("Plugin initialized");
        }
    }

    public static void main(String[] args)
            throws ClassNotFoundException {
        System.out.println("begin");

        Class<?> literal = Plugin.class;
        System.out.println("literal=" + literal.getSimpleName());

        Class<?> loaded = Class.forName(
                Plugin.class.getName(),
                false,
                Plugin.class.getClassLoader());
        System.out.println("loaded same=" + (literal == loaded));

        Class<?> initialized = Class.forName(Plugin.class.getName());
        System.out.println("initialized same=" +
                (literal == initialized));
        System.out.println("version=" + Plugin.version);
    }
}
~~~

~~~bash
javac -encoding UTF-8 ClassInitializationDemo.java
java ClassInitializationDemo
~~~

Stdout:

~~~text
begin
literal=Plugin
loaded same=true
Plugin initialized
initialized same=true
version=17
~~~

Static block chỉ chạy khi Plugin được initialize. Class literal và `forName(..., false, ...)` không tự yêu cầu initialization. `forName(String)` là điểm kích hoạt trong demo.

Không nhầm “class được nạp” với “class đã khởi tạo” hay “ordinary object đã được tạo”.

## 24. Class loader là một phần của runtime type identity

Một runtime class được nhận diện bởi **binary name và defining class loader**. Hai Class objects có thể có cùng `getName()` string nhưng **khác runtime identity** nếu được định nghĩa bởi các class loaders khác nhau.

Hệ quả:

- Không dùng tên string đơn lẻ làm bằng chứng hai runtime classes giống nhau.
- Trong ứng dụng đơn giản, `Person.class == new Person().getClass()` là mô hình đúng.
- Với plugins/containers/test class loaders, có thể gặp ClassCastException dù class names nhìn giống, vì runtime types khác.
- `Class.getClassLoader()` có thể trả null đối với bootstrap-loaded classes; đó là semantics API, không có nghĩa Class object không tồn tại.

`Class.forName` cần binary name hợp lệ. Nested class thường có `$` trong binary name, và array type names có dạng mã hóa khác `"java.lang.String[]"`.

## 25. Type erasure: hai generic objects có thể có cùng Class token

~~~java
java.util.List<String> strings = new java.util.ArrayList<>();
java.util.List<Integer> integers = new java.util.ArrayList<>();
~~~

`strings.getClass() == integers.getClass()` true; cả hai là ArrayList runtime class.

### Ví dụ chạy

Tạo **`GenericClassDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class GenericClassDemo {
    static final class Box<T> {
        private final T value;

        Box(T value) {
            this.value = value;
        }

        T value() {
            return value;
        }
    }

    public static void main(String[] args) {
        List<String> strings = new ArrayList<>();
        List<Integer> integers = new ArrayList<>();

        Box<String> word = new Box<>("Java");
        Box<Integer> number = new Box<>(17);

        System.out.println("same List Class=" +
                (strings.getClass() == integers.getClass()));
        System.out.println("same Box Class=" +
                (word.getClass() == number.getClass()));
        System.out.println("word=" + word.value());
        System.out.println("number=" + number.value());
    }
}
~~~

~~~bash
javac -encoding UTF-8 GenericClassDemo.java
java GenericClassDemo
~~~

Stdout:

~~~text
same List Class=true
same Box Class=true
word=Java
number=17
~~~

Generics vẫn có ích cho type checking compile-time. Nhưng `getClass()` không tạo một Class object mới cho từng use với type arguments.

## 26. Record, enum và sealed type có Class metadata

Java 17 hỗ trợ:

~~~java
record Point(int x, int y) {}
enum Color { RED, BLUE }
sealed interface Result permits Success, Failure {}
record Success() implements Result {}
record Failure() implements Result {}
~~~

`Point.class.isRecord()` true; `Color.class.isEnum()` true; `Result.class.isInterface()` và `Result.class.isSealed()` đều true.

### Ví dụ chạy

Tạo **`ModernMetadataDemo.java`**:

~~~java
public class ModernMetadataDemo {
    record Point(int x, int y) {}
    enum Color { RED, BLUE }

    sealed interface Result permits Success, Failure {}
    record Success() implements Result {}
    record Failure() implements Result {}

    public static void main(String[] args) {
        System.out.println("record=" + Point.class.isRecord());
        System.out.println("enum=" + Color.class.isEnum());
        System.out.println("interface=" +
                Result.class.isInterface());
        System.out.println("sealed=" +
                Result.class.isSealed());

        Object point = new Point(1, 2);
        System.out.println("point runtime=" +
                (point.getClass() == Point.class));
    }
}
~~~

~~~bash
javac -encoding UTF-8 ModernMetadataDemo.java
java ModernMetadataDemo
~~~

Stdout:

~~~text
record=true
enum=true
interface=true
sealed=true
point runtime=true
~~~

Một metadata token nói Point là record, nhưng không chứa riêng component values 1,2 của object point.

## 27. Class object có thể dùng làm Map key hoặc lock, nhưng cần thận trọng

Class object là Object, có identity và monitor. Có thể lưu:

~~~java
java.util.Map<Class<?>, String> labels =
        new java.util.HashMap<>();

labels.put(String.class, "text");
labels.put(Integer.class, "integer");
~~~

Hoặc một đoạn `synchronized (SomeClass.class) { ... }` sẽ khóa monitor của Class object.

Tuy nhiên dùng public Class objects làm lock có thể gây contention/deadlock với code không liên quan, đặc biệt `Object.class` hay `String.class`. Nên ưu tiên **private lock object** hoặc concurrency abstraction phù hợp.

Không suy ra mọi instance method trở thành thread-safe chỉ vì class có Class token hay một static method được synchronized.

## 28. Reflection introspection khác reflection invocation

Những việc **đọc metadata**:

~~~java
Class<?> type = Person.class;
type.getDeclaredMethods();
type.getDeclaredFields();
~~~

không trực tiếp tạo Person instance.

Những việc **có thể thực thi hoặc thay đổi state**:

- `Constructor.newInstance(...)`: tạo object, chạy constructor.
- `Method.invoke(target, args...)`: gọi method, có thể có side effects.
- `Field.set(target, value)`: có thể sửa state khi được phép.
- `Class.forName(String)`: có thể khởi tạo class và chạy static initializers.

Không nên coi mọi reflection operation là “chỉ xem metadata, không tác động gì”. Việc dùng reflection vào private members còn bị chi phối bởi accessibility và Java module system.

## 29. Những lỗi thường gặp

| Hiểu nhầm | Điều đúng |
| --- | --- |
| “`Foo.class` tạo Foo instance.” | Trả Class object. |
| “`Foo.class` chính là file Foo.class.” | Là Java class literal expression. |
| “Class object chứa tất cả Foo instances.” | Mô tả runtime type, không phải registry instances. |
| “`Class<Foo>` là Foo object.” | Class token của Foo có runtime class Class. |
| “`String.class` là String object.” | Là Class object mô tả String. |
| “`Class.class.getClass()` tạo chuỗi vô hạn.” | Bằng Class.class. |
| “`getClass()` trả declared variable type.” | Trả actual runtime class. |
| “`getClass()` trên null trả null.” | Ném NPE. |
| “`Object.class` đại diện mọi objects.” | Mô tả Object type. |
| “Primitive int cũng có instance methods.” | Primitive không là Object instance. |
| “`int.class` bằng `Integer.class`.” | Hai Class tokens khác nhau. |
| “Array không có Class token.” | Có, và `isArray()` là true. |
| “Interface không có metadata.” | `SomeInterface.class` có Class object. |
| “`isAssignableFrom` có thể đọc theo bất kỳ chiều.” | Target class token ở bên trái lời gọi. |
| “Class token tự tạo object khi đọc.” | Không. |
| “`getDeclaredField` cho luôn field value.” | Trả Field metadata; value cần target/access. |
| “Reflection cho quyền đọc mọi private field.” | Bị giới hạn bởi access/module rules. |
| “`Foo.class` chắc chắn chạy static block.” | Không tự bắt buộc initialize Foo. |
| “`Class.forName(String)` không có tác dụng phụ.” | Có thể initialize class. |
| “Cùng `getName()` thì cùng runtime type.” | Defining class loaders có thể khác. |
| “Generics tạo riêng Class object cho `List<String>`.” | Type erasure, runtime List implementation type vẫn chung. |

## 30. Bài tập 1 — Hai instances và một Class token

~~~java
class Book {}
Book a = new Book();
Book b = new Book();
Class<Book> type = Book.class;
~~~

**Đáp án:** Có hai Book objects, trong cùng loader context thông thường có một Class object cho Book runtime type. `a == b` false; `a.getClass() == b.getClass()` true; `type == a.getClass()` true.

## 31. Bài tập 2 — Runtime type qua Object

~~~java
Object a = "hello";
Object b = String.class;
~~~

**Đáp án:** `a.getClass() == String.class` true, `b.getClass() == Class.class` true. `b` là Class object mô tả String, không phải String instance.

## 32. Bài tập 3 — Exact vs subtype

~~~java
class Animal {}
class Dog extends Animal {}
Animal dog = new Dog();
~~~

**Đáp án:** `dog.getClass() == Animal.class` false; `dog.getClass() == Dog.class` true; `dog instanceof Animal` true; `dog instanceof Dog` true.

## 33. Bài tập 4 — Primitive, wrapper và array

Dự đoán:

~~~java
int.class == Integer.class;
int[].class.isArray();
int[].class.getComponentType() == int.class;
Integer.class.isPrimitive();
void.class.isPrimitive();
~~~

**Đáp án:** Lần lượt `false`, `true`, `true`, `false`, `true`.

## 34. Bài tập 5 — Assignability

Với `Dog extends Animal`:

~~~java
Animal.class.isAssignableFrom(Dog.class);
Dog.class.isAssignableFrom(Animal.class);
Object.class.isAssignableFrom(Dog.class);
Dog.class.isInstance(new Animal());
~~~

**Đáp án:** `true`, `false`, `true`, `false`. `isAssignableFrom` nhận hai Class tokens; `isInstance` nhận một object value.

## 35. Bài tập 6 — Metadata không phải instance value

~~~java
class Account {
    public int balance;
}
~~~

Hai Accounts có balances lần lượt 10/20. `Field f = Account.class.getField("balance")` đại diện **một field declaration**, nhưng `f.getInt(account1)`/`f.getInt(account2)` đọc hai values khác nhau.

**Giải thích:** Ordinary instance state thuộc từng object, còn Class và Field objects cung cấp runtime metadata về declarations.

## 36. Bài tập 7 — Class initialization

Một class:

~~~java
class Config {
    static {
        System.out.println("Config initialized");
    }
}
~~~

Chương trình trước dùng `Config.class`, sau gọi `Class.forName("Config")` trong cùng loader context thông thường.

**Đáp án:** Class literal không tự buộc initialization. `Class.forName(String)` yêu cầu initialization nếu class chưa initialized, làm block in một lần. Nếu Config đã initialize bởi thao tác khác, không in lại. Trong package thật, dùng binary name đầy đủ.

## 37. Bài tập 8 — Generic type erasure

~~~java
java.util.List<String> a = new java.util.ArrayList<>();
java.util.List<Integer> b = new java.util.ArrayList<>();
System.out.println(a.getClass() == b.getClass());
~~~

**Đáp án:** `true`. Cùng runtime ArrayList class, dù compile-time generic types khác. Compiler vẫn bảo vệ `List<String>` không cho thêm Integer qua type-safe API.

## 38. Bài tập 9 — Có thể cast Class token thành String instance không?

~~~java
Class<String> token = String.class;
// String value = (String) (Object) token;
~~~

Nếu bỏ comment, phép cast qua Object có thể biên dịch nhưng ném `ClassCastException` vì token là Class object, không phải String instance. Cast **không tạo hoặc biến đổi ordinary object**.

## 39. Bài tập 10 — Class của Class

~~~java
Class<?> token = Class.class;
System.out.println(token.getClass() == Class.class);
System.out.println(token.getSuperclass() == Object.class);
~~~

**Đáp án:**

~~~text
true
true
~~~

`Class` kế thừa Object, và `Class.class` chính nó cũng là Class object.

## 40. Checklist cuối bài

- [ ] Tôi phân biệt class declaration, ordinary instance và Class object.
- [ ] Tôi biết `class`, `Class` và `.class` là ba ký hiệu khác nhau.
- [ ] Tôi không nhầm file bytecode với class literal.
- [ ] Tôi biết Class extends Object.
- [ ] Tôi hiểu `Class.class.getClass() == Class.class`.
- [ ] Tôi biết nhiều instances cùng runtime type dùng chung Class token trong loader scope.
- [ ] Tôi không nghĩ Class object có danh sách tất cả instances.
- [ ] Tôi biết `Object.class` chỉ mô tả Object type.
- [ ] Tôi biết `getClass()` trả actual runtime type.
- [ ] Tôi biết `getClass()` trên null ném NPE.
- [ ] Tôi phân biệt exact runtime type với subtype compatibility.
- [ ] Tôi biết `Class<T>` và `Class<?>`.
- [ ] Tôi biết primitive, void, array và interface types có Class objects.
- [ ] Tôi không đồng nhất primitive token với wrapper token.
- [ ] Tôi dùng `Class.isInstance`, `isAssignableFrom`, `cast` đúng.
- [ ] Tôi phân biệt Class metadata với instance field values.
- [ ] Tôi hiểu `getDeclared...` và public `get...` APIs khác nhau.
- [ ] Tôi biết reflective construction khác lấy Class token.
- [ ] Tôi tránh API deprecated Class.newInstance.
- [ ] Tôi hiểu `.class` không tự chạy static initializer.
- [ ] Tôi biết `Class.forName(String)` có initialization semantics.
- [ ] Tôi hiểu class loader identity và type erasure.
- [ ] Tôi biết Class.isRecord/isEnum/isSealed trong Java 17.
- [ ] Tôi biết reflection access có giới hạn và có thể có side effects.
- [ ] Tôi giải thích được stdout các ví dụ độc lập ở trên.

**Kết luận:** **Class** là bản mô tả kiểu trong Java, **ordinary object** là thể hiện với identity và state, còn **`java.lang.Class<?>` object** là đối tượng runtime metadata đại diện cho một type. `.class` lấy token của kiểu được nêu trong source, `getClass()` trả actual runtime type của một non-null object và `Class.forName` hỗ trợ dynamic lookup với class-initialization semantics riêng. Không nhầm metadata với object data, và không nhầm “cùng tên kiểu” với cùng runtime identity khi có nhiều class loaders.
