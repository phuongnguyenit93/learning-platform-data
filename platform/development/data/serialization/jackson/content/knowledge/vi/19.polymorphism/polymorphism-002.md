# Phân biệt kiểu khai báo Java và kiểu thực tế của đối tượng

Trong Java, một biến có **kiểu khai báo** (declared type) và object mà biến đang tham chiếu có **kiểu thực tế** (runtime type). Hai kiểu này có thể khác nhau khi sử dụng kế thừa và đa hình.

Ví dụ:

~~~java
Animal animal = new Dog();
~~~

- Kiểu khai báo của biến animal là Animal. Compiler dùng kiểu này để kiểm tra những method và field mà code được phép truy cập.
- Kiểu thực tế của object là Dog. JVM dùng kiểu thực tế khi thực hiện dynamic method dispatch, và Jackson thường dựa vào kiểu runtime để serialize giá trị theo cơ chế dynamic typing mặc định.

Sự khác biệt này rất quan trọng khi dùng Jackson. Serialization có thể nhìn thấy các thuộc tính của lớp con, nhưng khi deserialization từ JSON về một kiểu cha hoặc interface, Jackson cần biết phải tạo lớp con nào. JSON thông thường chỉ chứa tên field và value; nó không tự mang thông tin class Java cần khởi tạo.

## 1. Kiểu khai báo và kiểu thực tế trong Java

### 1.1. Kiểu khai báo

Kiểu khai báo là kiểu được ghi khi khai báo biến, tham số, field hoặc kiểu trả về:

~~~java
Animal animal;
List<Animal> animals;
void feed(Animal animal) { }
Animal findAnimal() { ... }
~~~

Kiểu này quyết định:
- Compiler cho phép truy cập những method và field nào.
- Method overload nào được chọn tại thời điểm biên dịch.
- Kiểu dữ liệu mà API công bố cho caller.
- Kiểm tra kiểu tĩnh và nhiều phép chuyển đổi hợp lệ.

Nếu Animal chỉ khai báo method makeSound(), code dùng biến animal có thể gọi makeSound(). Nếu Dog có method fetch() nhưng Animal không có method đó, compiler không cho gọi trực tiếp:

~~~java
Animal animal = new Dog();

// Hợp lệ nếu makeSound() được khai báo trong Animal.
animal.makeSound();

// Không biên dịch nếu fetch() chỉ có trong Dog.
// animal.fetch();
~~~

Muốn gọi method riêng của Dog, cần có một cách kiểm tra hoặc chuyển kiểu an toàn.

### 1.2. Kiểu thực tế của object

Kiểu thực tế là class của instance được tạo trong runtime:

~~~java
Animal animal = new Dog();

System.out.println(animal.getClass().getName());
~~~

Kết quả là tên class Dog (kèm package nếu in bằng getName()).

Một biến kiểu cha có thể tham chiếu nhiều kiểu con:

~~~java
Animal first = new Dog();
Animal second = new Cat();
~~~

Cả hai biến có cùng kiểu khai báo Animal nhưng kiểu thực tế lần lượt là Dog và Cat.

### 1.3. Dynamic method dispatch

Khi gọi một method instance đã được override, JVM chọn implementation theo kiểu thực tế của object:

~~~java
abstract class Animal {
    public abstract String makeSound();
}

class Dog extends Animal {
    @Override
    public String makeSound() {
        return "Woof";
    }

    public void fetch() {
        System.out.println("Dog fetches the ball");
    }
}

class Cat extends Animal {
    @Override
    public String makeSound() {
        return "Meow";
    }
}
~~~

~~~java
Animal animal = new Dog();

System.out.println(animal.makeSound());
~~~

Kết quả là Woof, vì object thực tế là Dog. Compiler xác nhận method makeSound() có trong Animal; JVM gọi implementation override của Dog.

Đây là đa hình trong Java: code có thể làm việc qua kiểu cha, trong khi hành vi thực tế đến từ lớp con.

### 1.4. Field và static method không có dynamic dispatch như instance method

Không nên suy rộng dynamic dispatch cho mọi thành viên class. Field bị che khuất (field hiding) và static method được chọn theo kiểu tham chiếu/kiểu khai báo tại thời điểm biên dịch, không theo kiểu runtime như method instance được override.

~~~java
class Parent {
    public String label = "parent";

    public static String category() {
        return "Parent";
    }
}

class Child extends Parent {
    public String label = "child";

    public static String category() {
        return "Child";
    }
}
~~~

~~~java
Parent value = new Child();

System.out.println(value.label);
System.out.println(value.category());
~~~

Các biểu thức trên được phân giải theo kiểu Parent và in ra giá trị của Parent. Vì vậy, khi giải thích đa hình, cần nói rõ đang xét instance method được override.

## 2. Kiểu khai báo và kiểu runtime khi Jackson serialize

Jackson Databind thường dùng runtime type để tìm serializer phù hợp khi serialize một object với dynamic typing mặc định.

Ví dụ:

~~~java
abstract class Animal {
    private String name;

    public Animal() {
    }

    public Animal(String name) {
        this.name = name;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }
}

class Dog extends Animal {
    private boolean trained;

    public Dog() {
    }

    public Dog(String name, boolean trained) {
        super(name);
        this.trained = trained;
    }

    public boolean isTrained() {
        return trained;
    }

    public void setTrained(boolean trained) {
        this.trained = trained;
    }
}
~~~

Biến được khai báo bằng kiểu cha nhưng giữ object Dog:

~~~java
Animal animal = new Dog("Milo", true);

ObjectMapper mapper = new ObjectMapper();
String json = mapper.writeValueAsString(animal);

System.out.println(json);
~~~

Với cấu hình serialization động thông thường, JSON có thể chứa cả property kế thừa name và property riêng trained của Dog:

~~~json
{
  "name": "Milo",
  "trained": true
}
~~~

Điều này cho thấy kiểu khai báo Animal không nhất thiết giới hạn output chỉ còn các property của Animal. Jackson có thể nhận ra object thực tế là Dog và dùng serializer của Dog.

### 2.1. Property có kiểu khai báo là lớp cha

Xét một object khác:

~~~java
public class Zoo {
    private Animal resident;

    public Animal getResident() {
        return resident;
    }

    public void setResident(Animal resident) {
        this.resident = resident;
    }
}
~~~

Gán object Dog:

~~~java
Zoo zoo = new Zoo();
zoo.setResident(new Dog("Milo", true));

String json = mapper.writeValueAsString(zoo);
~~~

Với dynamic typing thông thường, Jackson có thể serialize resident theo kiểu runtime Dog và ghi các property mà Dog cung cấp.

Điểm này giúp một field có kiểu cha chứa nhiều loại object con. Tuy nhiên, output JSON có thêm property của lớp con không có nghĩa Jackson đã ghi thông tin để xác định lớp con khi đọc lại.

### 2.2. Serialization không tự động bảo đảm round trip

Giả sử JSON được ghi ra:

~~~json
{
  "name": "Milo",
  "trained": true
}
~~~

Nếu đọc lại với kiểu cha:

~~~java
Animal restored = mapper.readValue(json, Animal.class);
~~~

Jackson không có đủ thông tin để biết phải tạo Dog hay một lớp con khác. Animal là abstract nên không thể khởi tạo trực tiếp. Ngay cả khi Animal là concrete class, Jackson cũng không tự suy luận rằng object ban đầu từng là Dog chỉ từ việc JSON có property trained.

Serialization thành công và deserialization về đúng subtype là hai yêu cầu khác nhau.

Nếu cần round trip qua kiểu cha/interface, JSON phải mang thông tin loại (type information), hoặc ứng dụng phải cung cấp một quy tắc lựa chọn subtype khác.

## 3. Jackson deserialization cần kiểu đích

### 3.1. Đọc vào kiểu concrete đã biết

Nếu caller biết chính xác kiểu đích là Dog, không cần discriminator:

~~~java
Dog dog = mapper.readValue(json, Dog.class);
~~~

Jackson tạo Dog và ánh xạ property tương ứng. Đây là trường hợp đơn giản vì kiểu runtime mong muốn đã được cung cấp qua kiểu đích.

### 3.2. Đọc vào kiểu cha hoặc interface

Nếu caller chỉ biết kiểu Animal:

~~~java
Animal animal = mapper.readValue(json, Animal.class);
~~~

Jackson cần biết class concrete nào sẽ được tạo. Nếu Animal là abstract class hoặc interface, mapper không thể tự khởi tạo nó chỉ dựa vào kiểu khai báo.

Các cách giải quyết phổ biến:
- Thêm discriminator vào JSON bằng @JsonTypeInfo.
- Đăng ký subtype và dùng logical type name.
- Dùng custom deserializer hoặc abstract type mapping khi có quy tắc riêng.
- Đọc vào JsonNode rồi tự quyết định class đích dựa trên dữ liệu.
- Nếu hợp đồng đã xác định một class cụ thể, gọi readValue với class đó.

Không nên giả định Jackson sẽ tự chọn subtype dựa trên tên property riêng của lớp con. Việc suy luận kiểu từ sự hiện diện của một field có thể mơ hồ và dễ hỏng khi schema thay đổi.

## 4. Dùng @JsonTypeInfo để giữ thông tin subtype

Cách phổ biến để deserialize đa hình là thêm một property discriminator vào JSON. Jackson dùng giá trị đó để chọn lớp con.

~~~java
import com.fasterxml.jackson.annotation.JsonSubTypes;
import com.fasterxml.jackson.annotation.JsonTypeInfo;

@JsonTypeInfo(
        use = JsonTypeInfo.Id.NAME,
        include = JsonTypeInfo.As.PROPERTY,
        property = "kind"
)
@JsonSubTypes({
        @JsonSubTypes.Type(value = Dog.class, name = "dog"),
        @JsonSubTypes.Type(value = Cat.class, name = "cat")
})
public abstract class Animal {
    private String name;

    public Animal() {
    }

    public Animal(String name) {
        this.name = name;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }
}
~~~

Các class con:

~~~java
public class Dog extends Animal {
    private boolean trained;

    public Dog() {
    }

    public Dog(String name, boolean trained) {
        super(name);
        this.trained = trained;
    }

    public boolean isTrained() {
        return trained;
    }

    public void setTrained(boolean trained) {
        this.trained = trained;
    }
}
~~~

~~~java
public class Cat extends Animal {
    private int lives;

    public Cat() {
    }

    public Cat(String name, int lives) {
        super(name);
        this.lives = lives;
    }

    public int getLives() {
        return lives;
    }

    public void setLives(int lives) {
        this.lives = lives;
    }
}
~~~

Khi serialize Dog qua biến kiểu Animal:

~~~java
Animal animal = new Dog("Milo", true);
String json = mapper.writeValueAsString(animal);
~~~

JSON có thể mang discriminator:

~~~json
{
  "kind": "dog",
  "name": "Milo",
  "trained": true
}
~~~

Khi đọc:

~~~java
Animal restored = mapper.readValue(json, Animal.class);

System.out.println(restored.getClass().getSimpleName());
~~~

Jackson đọc kind = dog, tìm subtype Dog đã đăng ký và tạo object Dog. Caller vẫn nhận kiểu khai báo Animal nhưng object thực tế sau khi đọc là Dog.

### 4.1. Id.NAME và tên subtype logic

JsonTypeInfo.Id.NAME dùng một tên logic như dog hoặc cat thay cho tên class đầy đủ.

Có thể khai báo subtype ngay trên @JsonSubTypes hoặc đặt @JsonTypeName trên class con:

~~~java
@JsonTypeName("dog")
public class Dog extends Animal {
    // Các property của Dog.
}
~~~

Tên logical type là một phần của hợp đồng JSON. Nên chọn tên ổn định, dễ hiểu và không gắn với package nội bộ của ứng dụng.

Nếu class được refactor hoặc chuyển package, JSON vẫn có thể giữ kind = dog miễn là subtype mapping tiếp tục đăng ký tên đó.

### 4.2. include = As.PROPERTY

Với As.PROPERTY, discriminator được biểu diễn như một property trong JSON object:

~~~json
{
  "kind": "cat",
  "name": "Mimi",
  "lives": 9
}
~~~

Jackson dùng kind để chọn Cat. Theo cách xử lý mặc định, discriminator phục vụ quá trình chọn subtype và không nhất thiết được gán vào một field Java cùng tên.

Nếu ứng dụng cần giữ discriminator như một property dữ liệu thông thường, có thể xem xét thuộc tính visible của @JsonTypeInfo. Chỉ bật khi model thực sự cần truy cập giá trị đó; nếu không, để metadata được Jackson quản lý sẽ đơn giản hơn.

### 4.3. Đặt type metadata ở lớp cha hoặc property

Có thể đặt @JsonTypeInfo trên base class/interface để các subtype của kiểu đó dùng chung chính sách.

Cũng có thể đặt trên một property cụ thể:

~~~java
public class EventEnvelope {

    @JsonTypeInfo(
            use = JsonTypeInfo.Id.NAME,
            include = JsonTypeInfo.As.PROPERTY,
            property = "eventType"
    )
    @JsonSubTypes({
            @JsonSubTypes.Type(value = UserCreated.class, name = "user-created"),
            @JsonSubTypes.Type(value = UserDeleted.class, name = "user-deleted")
    })
    private DomainEvent event;

    // Getter và setter.
}
~~~

Cách đặt trên property hữu ích khi chỉ một nhánh của object graph cần đa hình. Cần bảo đảm các subtype được đăng ký trong phạm vi metadata đó.

## 5. Phân biệt kiểu khai báo trong collection và generic

Một collection có thể được khai báo theo kiểu cha:

~~~java
List<Animal> animals = new ArrayList<>();
animals.add(new Dog("Milo", true));
animals.add(new Cat("Mimi", 9));
~~~

Kiểu khai báo của collection là List<Animal>. Kiểu thực tế của từng phần tử lần lượt là Dog và Cat.

Khi serialize, Jackson có thể dùng runtime type của từng phần tử theo dynamic typing mặc định. Nếu cần deserialize lại thành List<Animal>, mỗi phần tử cần có thông tin subtype hoặc một cơ chế chọn kiểu cụ thể.

~~~java
String json = mapper.writeValueAsString(animals);
~~~

Để đọc generic type, dùng TypeReference:

~~~java
List<Animal> restored = mapper.readValue(
        json,
        new TypeReference<List<Animal>>() {}
);
~~~

TypeReference giữ thông tin kiểu generic List<Animal> để Jackson biết root là collection và kiểu khai báo của phần tử là Animal.

Tuy nhiên, TypeReference không tự cho biết mỗi phần tử là Dog hay Cat. Thông tin subtype vẫn phải đến từ @JsonTypeInfo, custom deserializer hoặc quy tắc khác của ứng dụng.

Ví dụ JSON có discriminator cho từng phần tử:

~~~json
[
  {
    "kind": "dog",
    "name": "Milo",
    "trained": true
  },
  {
    "kind": "cat",
    "name": "Mimi",
    "lives": 9
  }
]
~~~

Jackson có thể đọc thành List<Animal> với phần tử đầu là Dog và phần tử thứ hai là Cat khi subtype mapping đã được khai báo.

## 6. Kiểu khai báo có thể điều khiển serialization khi dùng static typing

Mặc định, Jackson thường dùng dynamic typing để tìm serializer phù hợp với object runtime. Tuy nhiên, ứng dụng có thể yêu cầu serializer dựa trên kiểu khai báo.

Ví dụ:

~~~java
public class Zoo {
    @JsonSerialize(typing = JsonSerialize.Typing.STATIC)
    private Animal resident;

    public Animal getResident() {
        return resident;
    }

    public void setResident(Animal resident) {
        this.resident = resident;
    }
}
~~~

Với static typing, Jackson giải quyết serializer theo kiểu khai báo Animal của property. Những property chỉ có ở Dog có thể không xuất hiện trong output, tùy serializer và cấu hình cụ thể.

Một lựa chọn ở cấp mapper là MapperFeature.USE_STATIC_TYPING. Khi bật, Jackson ưu tiên kiểu khai báo trong các trường hợp áp dụng thay vì tự động chọn serializer theo kiểu runtime.

~~~java
ObjectMapper mapper = JsonMapper.builder()
        .enable(MapperFeature.USE_STATIC_TYPING)
        .build();
~~~

Static typing có thể hữu ích khi muốn output tuân theo một contract base type ổn định. Nhưng cần kiểm tra ảnh hưởng với interface/abstract type, custom serializer, generic type và type metadata. Không bật global static typing chỉ để giải quyết một property nếu annotation hoặc writer cấu hình theo phạm vi hẹp đã đủ.

### 6.1. @JsonSerialize(as = ...) và kiểu serialization được chỉ định

Annotation JsonSerialize có thuộc tính as để yêu cầu Jackson xem giá trị qua một kiểu cụ thể trong serialization:

~~~java
@JsonSerialize(as = Animal.class)
private Animal resident;
~~~

Cách khai báo này có thể giới hạn serializer được chọn theo kiểu chỉ định. Kết quả phụ thuộc kiểu, serializer và cấu hình polymorphic đi kèm; cần kiểm thử JSON thực tế trước khi dùng làm hợp đồng.

Đừng nhầm:
- Kiểu khai báo Java là thông tin trong source code.
- Runtime type là class thực tế của object.
- Static typing là lựa chọn về cách Jackson chọn serializer.
- @JsonTypeInfo là metadata giúp Jackson nhận diện subtype trong JSON khi cần deserialize đa hình.

Bốn khái niệm có liên quan nhưng giải quyết các câu hỏi khác nhau.

## 7. Chuyển kiểu an toàn để truy cập hành vi riêng của lớp con

Trong Java, nếu biến có kiểu cha nhưng cần gọi method riêng của lớp con, có thể dùng instanceof pattern matching:

~~~java
Animal animal = new Dog("Milo", true);

if (animal instanceof Dog dog) {
    System.out.println(dog.isTrained());
    dog.fetch();
}
~~~

Kiểm tra instanceof xác nhận object runtime có thể được xem là Dog. Pattern variable dog có kiểu Dog bên trong nhánh đúng.

Cách này hữu ích khi code thực sự cần hành vi riêng của subtype. Nếu thường xuyên phải kiểm tra nhiều subtype trong business logic, có thể cân nhắc thiết kế method đa hình trên base class/interface để tránh phụ thuộc vào nhiều phép cast.

Jackson không tự gọi các method riêng của subtype chỉ vì biến Java có kiểu cha. Jackson dùng metadata, serializer và property được nhận diện để chuyển đổi dữ liệu.

## 8. Khi nào chỉ cần kiểu concrete, khi nào cần polymorphic metadata?

| Tình huống | Kiểu đọc | Có cần discriminator? |
|---|---|---|
| JSON luôn là Dog | Dog.class | Không |
| JSON có thể là Dog hoặc Cat, caller chỉ biết Animal | Animal.class | Có, hoặc custom subtype resolver |
| JSON là List<Dog> | TypeReference<List<Dog>> | Không cần cho subtype nếu mọi phần tử đều là Dog |
| JSON là List<Animal> có nhiều subtype | TypeReference<List<Animal>> | Cần thông tin subtype hoặc quy tắc tương đương |
| Property khai báo là Animal nhưng có thể chứa nhiều lớp con | Kiểu property Animal | Cần metadata nếu muốn deserialize lại đúng subtype |
| Ứng dụng chỉ cần đọc một số field, chưa cần tạo class con | JsonNode | Có thể tự quyết định sau khi đọc discriminator |

Nếu kiểu concrete đã biết, hãy truyền kiểu concrete cho readValue. Nếu hợp đồng cho phép nhiều subtype qua một kiểu cha, hãy công bố cách nhận diện subtype rõ ràng.

## 9. Unknown subtype và chính sách fallback

Nếu JSON gửi discriminator không được đăng ký:

~~~json
{
  "kind": "bird",
  "name": "Rio"
}
~~~

Trong khi mapping chỉ đăng ký dog và cat, Jackson thường báo lỗi không nhận diện type id. Đây là lựa chọn giúp phát hiện dữ liệu không thuộc contract đã biết.

Có thể cấu hình defaultImpl trong @JsonTypeInfo để dùng một class mặc định trong một số trường hợp:

~~~java
@JsonTypeInfo(
        use = JsonTypeInfo.Id.NAME,
        include = JsonTypeInfo.As.PROPERTY,
        property = "kind",
        defaultImpl = UnknownAnimal.class
)
~~~

Fallback chỉ nên dùng nếu UnknownAnimal có semantics rõ ràng và ứng dụng biết cách xử lý. Không nên ánh xạ một subtype không biết thành một subtype có quyền thực hiện hành động quan trọng.

Nếu hệ thống cần tương thích với subtype mới từ server mới, hãy thiết kế chính sách unknown một cách có chủ đích: từ chối, giữ payload dạng tree, hoặc tạo một loại unknown riêng để xử lý an toàn.

## 10. An toàn khi deserialize polymorphic JSON

Type metadata ảnh hưởng đến class mà Jackson tạo. Vì vậy, không nên cho JSON không đáng tin cậy tự chỉ định tùy ý tên class Java cần khởi tạo.

Một số nguyên tắc:
- Ưu tiên JsonTypeInfo.Id.NAME với danh sách subtype được đăng ký rõ ràng.
- Dùng logical type name ổn định như dog, cat hoặc user-created.
- Tránh bật default typing không giới hạn cho dữ liệu từ client hoặc nguồn không đáng tin cậy.
- Không dùng tên class đầy đủ làm contract nếu không có lý do tương thích rõ ràng.
- Chỉ đăng ký những subtype mà ứng dụng cho phép tạo.
- Kiểm tra unknown type id và lỗi mapping.
- Với dữ liệu lưu trữ lâu dài, duy trì mapping tương thích khi refactor class.

Jackson có các cơ chế bảo vệ và giới hạn polymorphic type tùy phiên bản, nhưng ứng dụng vẫn phải quyết định tập kiểu nào được phép deserialize. Type discriminator là dữ liệu đầu vào, không phải bằng chứng rằng class được yêu cầu là an toàn.

## 11. Ví dụ hoàn chỉnh: serialize và deserialize qua kiểu cha

Ví dụ dùng base type Animal và hai subtype Dog, Cat:

~~~java
import com.fasterxml.jackson.annotation.JsonSubTypes;
import com.fasterxml.jackson.annotation.JsonTypeInfo;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.util.List;

@JsonTypeInfo(
        use = JsonTypeInfo.Id.NAME,
        include = JsonTypeInfo.As.PROPERTY,
        property = "kind"
)
@JsonSubTypes({
        @JsonSubTypes.Type(value = Dog.class, name = "dog"),
        @JsonSubTypes.Type(value = Cat.class, name = "cat")
})
abstract class Animal {
    private String name;

    public Animal() {
    }

    public Animal(String name) {
        this.name = name;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }
}

class Dog extends Animal {
    private boolean trained;

    public Dog() {
    }

    public Dog(String name, boolean trained) {
        super(name);
        this.trained = trained;
    }

    public boolean isTrained() {
        return trained;
    }

    public void setTrained(boolean trained) {
        this.trained = trained;
    }

    public void fetch() {
        System.out.println("Fetching");
    }
}

class Cat extends Animal {
    private int lives;

    public Cat() {
    }

    public Cat(String name, int lives) {
        super(name);
        this.lives = lives;
    }

    public int getLives() {
        return lives;
    }

    public void setLives(int lives) {
        this.lives = lives;
    }
}

public class PolymorphicJacksonDemo {

    public static void main(String[] args) throws Exception {
        ObjectMapper mapper = new ObjectMapper();

        // Kiểu khai báo là Animal, kiểu runtime là Dog.
        Animal dog = new Dog("Milo", true);

        String dogJson = mapper.writeValueAsString(dog);
        System.out.println(dogJson);

        // Kiểu khai báo khi đọc là Animal;
        // discriminator cho biết object thực tế cần tạo là Dog.
        Animal restoredDog = mapper.readValue(dogJson, Animal.class);

        System.out.println(restoredDog.getClass().getSimpleName());

        if (restoredDog instanceof Dog actualDog) {
            System.out.println(actualDog.isTrained());
            actualDog.fetch();
        }

        // Collection có kiểu khai báo List<Animal> và nhiều runtime subtype.
        List<Animal> animals = List.of(
                new Dog("Milo", true),
                new Cat("Mimi", 9)
        );

        String listJson = mapper.writeValueAsString(animals);

        List<Animal> restoredAnimals = mapper.readValue(
                listJson,
                new com.fasterxml.jackson.core.type.TypeReference<List<Animal>>() {}
        );

        for (Animal animal : restoredAnimals) {
            System.out.println(animal.getClass().getSimpleName());
        }
    }
}
~~~

Trong ví dụ:
1. Biến dog được khai báo là Animal nhưng giữ object Dog.
2. Jackson serialize object và ghi discriminator kind.
3. Khi đọc với Animal.class, Jackson dùng kind để chọn Dog.
4. Caller nhận kiểu khai báo Animal nhưng object runtime là Dog.
5. TypeReference giữ kiểu collection List<Animal>; discriminator của từng phần tử giúp khôi phục subtype tương ứng.

## 12. Kiểm thử sự khác nhau giữa declared type và runtime type

Nên kiểm thử cả output JSON lẫn kiểu thực tế sau khi đọc.

~~~java
@Test
void serializesSubtypeAndRestoresRuntimeType() throws Exception {
    Animal original = new Dog("Milo", true);

    String json = mapper.writeValueAsString(original);

    assertTrue(json.contains("\"kind\":\"dog\""));
    assertTrue(json.contains("\"trained\":true"));

    Animal restored = mapper.readValue(json, Animal.class);

    assertInstanceOf(Dog.class, restored);
    assertEquals("Milo", restored.getName());
    assertTrue(((Dog) restored).isTrained());
}
~~~

Với collection:

~~~java
@Test
void restoresDifferentSubtypesInAnimalList() throws Exception {
    List<Animal> original = List.of(
            new Dog("Milo", true),
            new Cat("Mimi", 9)
    );

    String json = mapper.writeValueAsString(original);

    List<Animal> restored = mapper.readValue(
            json,
            new TypeReference<List<Animal>>() {}
    );

    assertInstanceOf(Dog.class, restored.get(0));
    assertInstanceOf(Cat.class, restored.get(1));
}
~~~

Ngoài trường hợp hợp lệ, nên kiểm thử discriminator không biết, thiếu discriminator và property subtype sai kiểu. Các test này xác nhận hợp đồng đa hình hoạt động như mong muốn khi dữ liệu đầu vào thay đổi.

## 13. Những điều cần nhớ

- Kiểu khai báo được compiler dùng để kiểm tra cách code sử dụng biến.
- Kiểu thực tế là class của instance trong runtime.
- Instance method được override dùng dynamic dispatch theo kiểu thực tế.
- Field và static method không được dispatch như instance method.
- Jackson thường dùng runtime type khi serialize theo dynamic typing mặc định, nên property của lớp con có thể xuất hiện dù biến được khai báo bằng kiểu cha.
- Serialization có subtype property không tự bảo đảm deserialization biết subtype nào cần tạo.
- Khi đọc vào kiểu concrete, truyền Class cụ thể là đủ.
- Khi đọc vào abstract class/interface hoặc collection của kiểu cha, cần discriminator hoặc cơ chế chọn subtype khác.
- @JsonTypeInfo và @JsonSubTypes giúp công bố subtype mapping.
- TypeReference giữ generic type như List<Animal>, nhưng không tự xác định Dog hay Cat cho từng phần tử.
- Static typing có thể giới hạn serializer theo kiểu khai báo; cần kiểm thử output thực tế.
- Ưu tiên logical type name và subtype allowlist khi deserialize dữ liệu không đáng tin cậy.

Phân biệt kiểu khai báo và kiểu thực tế giúp hiểu vì sao Java có thể làm việc với nhiều subtype qua một interface, vì sao Jackson có thể serialize property riêng của lớp con, và vì sao deserialize ngược lại cần thông tin loại rõ ràng. Kiểu khai báo mô tả contract mà code sử dụng; kiểu runtime mô tả object đang tồn tại. Khi đưa dữ liệu qua JSON, ứng dụng phải quyết định thông tin nào cần được giữ lại để khôi phục đúng subtype.
