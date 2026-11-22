# Giới hạn khi trả về wildcard từ API trong Java Generics

## 1. Mục tiêu và vấn đề thực tế

Quy tắc **PECS** (*Producer Extends, Consumer Super*) giúp chọn wildcard cho các tham số generic: đối tượng dùng để **cung cấp dữ liệu** thường phù hợp với `? extends T`, còn đối tượng dùng để **nhận dữ liệu** thường phù hợp với `? super T`. Tuy nhiên, áp dụng PECS một cách máy móc cho **kiểu trả về của API** có thể khiến mã gọi API mất thông tin kiểu, bị hạn chế thao tác và phải truyền wildcard sang nhiều tầng mã khác.

Ví dụ:

```java
static List<? extends Number> numbers() {
    return List.of(1, 2, 3);
}
```

Lời gọi sau hợp lệ:

```java
List<? extends Number> result = numbers();
Number number = result.get(0);
```

Nhưng hai thao tác sau không hợp lệ:

```java
// List<Number> result = numbers(); // LỖI: kiểu trả về không bảo đảm List<Number>.
// numbers().add(4);               // LỖI: không biết kiểu phần tử thực tế.
```

Đây là những **giới hạn ở thời điểm biên dịch**, không nhất thiết là lỗi thiết kế trong mọi tình huống. Bài học phân biệt khi wildcard return hợp lý, khi nó khiến API khó sử dụng và cách viết chữ ký trả về rõ ràng hơn.

Sau khi học, bạn có thể:

- Giải thích thông tin kiểu mà `List<?>`, `List<? extends T>` và `List<? super T>` còn giữ lại cho caller.
- Phân biệt việc **trả về một giá trị** với vai trò producer/consumer của **đối tượng được trả về**.
- Hiểu vì sao `List<? extends T>` không đồng nghĩa với `List<T>` hoặc một danh sách bất biến.
- Thiết kế API trả về kiểu cụ thể, kiểu cha phù hợp hoặc phương thức generic `<T>` khi caller cần thông tin kiểu mạnh hơn.
- Nhận diện các trường hợp wildcard return hữu ích và tránh ép kiểu không kiểm tra.

## 2. Wildcard return là gì?

Giả sử có các class:

```java
class Animal {}
class Dog extends Animal {}
class Cat extends Animal {}
```

Và một thư viện cung cấp các phương thức sau:

```java
static List<Dog> dogs() {
    return List.of(new Dog());
}

static List<? extends Animal> animalsUnknownSubtype() {
    return dogs();
}

static List<?> unknownItems() {
    return dogs();
}
```

Chữ ký `List<Dog>` cho caller biết **chính xác đối số kiểu là `Dog`**. Chữ ký `List<? extends Animal>` chỉ cho biết đối số kiểu là một kiểu không xác định nhưng là subtype của `Animal`. Chữ ký `List<?>` không bảo đảm phần tử thuộc lớp cụ thể nào ngoài `Object`.

Một phương thức có thể trả về đối tượng runtime giống nhau ở cả ba trường hợp. Khác biệt chính là **hợp đồng kiểu mà Java cho caller sử dụng**.

### 2.1. Kiểu được công khai quyết định thao tác hợp lệ

Trong mã của thư viện, tác giả có thể biết rằng kết quả là `List<Dog>`. Khi công khai chữ ký `List<? extends Animal>`, thông tin **chính xác là `Dog`** không còn được bảo đảm cho người gọi:

```java
List<? extends Animal> animals = animalsUnknownSubtype();

Animal first = animals.get(0); // Hợp lệ.
// Dog dog = animals.get(0);   // Lỗi: giá trị chỉ được bảo đảm là Animal.
// animals.add(new Dog());     // Lỗi: có thể danh sách thực tế là List<Cat>.
```

Đối tượng runtime có thể chứa `Dog`; tuy nhiên, Java phải kiểm tra chương trình an toàn với **mọi kiểu** mà chữ ký cho phép, không chỉ kết quả ở một lần thực thi.

## 3. Vì sao không nên áp dụng PECS máy móc lên kiểu trả về?

Trong chữ ký:

```java
static void process(List<? extends Animal> source) { ... }
```

`source` là tham số đóng vai **producer** khi `process` cần đọc dữ liệu. Wildcard cận trên cho phép caller truyền `List<Dog>`, `List<Cat>` hay `List<Animal>` mà vẫn bảo đảm phần tử đọc được như `Animal`.

Nhưng trong chữ ký:

```java
static List<? extends Animal> getAnimals() { ... }
```

người gọi **nhận một đối tượng danh sách**. Sau khi nhận, họ có thể muốn đọc, lọc, sao chép, thêm phần tử, sắp xếp hoặc truyền kết quả đến phương thức khác. Nếu khai báo trả về chứa wildcard, mọi thao tác tiếp theo chịu các hạn chế tương ứng với wildcard đó.

Hai góc nhìn cần phân biệt:

1. **Phương thức trả về giá trị**: API sản xuất ra một đối tượng cho caller.
2. **Collection được trả về**: caller có thể dùng đối tượng đó để sản xuất hoặc tiêu thụ phần tử.

Không nên suy ra rằng vì phương thức là producer của đối tượng trả về nên kiểu trả về bắt buộc dùng `? extends T`. Hãy quyết định dựa trên **hợp đồng mà caller cần**.

Khuyến nghị thường gặp từ hướng dẫn Java Generics là **tránh wildcard ở kiểu trả về khi có thể**, vì caller phải tiếp tục xử lý kiểu chưa biết. Đây là nguyên tắc thiết kế API, không phải lệnh cấm cú pháp.

## 4. Trả về `List<?>`: mất thông tin về phần tử

Ví dụ:

```java
static List<?> loadItems() {
    return List.of("Java", "Generics");
}
```

Tại caller:

```java
List<?> values = loadItems();
Object item = values.get(0);       // Hợp lệ.
int count = values.size();         // Hợp lệ.

// String value = values.get(0);   // Lỗi biên dịch: chỉ bảo đảm Object.
// values.add("new element");      // Lỗi biên dịch: không rõ kiểu phần tử.
```

Về mặt kiểu, `List<?>` có thể biểu thị `List<String>`, `List<Integer>` hoặc nhiều kiểu khác. Do đó kết quả của `get` chỉ được bảo đảm là `Object`, và `add` không thể nhận một đối tượng non-null bất kỳ theo cách an toàn tổng quát.

### 4.1. Khi `List<?>` vẫn phù hợp

Kiểu trả về `List<?>` có thể hợp lý khi **ý nghĩa nghiệp vụ thực sự là một tập hợp có phần tử chưa biết hoặc dị thể** và caller chỉ cần các thao tác không phụ thuộc kiểu phần tử:

```java
static List<?> diagnosticValues() {
    return List.of("READY", 200, true);
}
```

Caller có thể in, đếm, hiển thị hoặc kiểm tra từng phần tử:

```java
for (Object value : diagnosticValues()) {
    System.out.println(value);
}
```

Nhưng nếu API thực sự bảo đảm mọi phần tử là `String`, công khai `List<String>` sẽ dễ dùng hơn `List<?>`.

### 4.2. Phân biệt `List<?>` với raw `List`

```java
List<?> safe = List.of("a", "b");
List raw = List.of("a", "b"); // Raw type, không nên dùng cho API mới.
```

`List<?>` vẫn duy trì hệ thống kiểm tra kiểu generic. Raw `List` bỏ qua một phần bảo vệ đó và có thể tạo unchecked warnings. Không nên thay wildcard return bằng raw type chỉ để làm compiler hết phàn nàn.

## 5. Trả về `List<? extends T>`: đọc được T nhưng khó ghi

Giả sử:

```java
static List<? extends Number> readNumbers() {
    return List.of(1, 2, 3);
}
```

Ở caller:

```java
List<? extends Number> result = readNumbers();

Number first = result.get(0); // Hợp lệ.
Object same = result.get(0);  // Hợp lệ.
// result.add(4);             // Lỗi: chưa chắc kiểu phần tử là Integer.
// result.add(2.5);           // Lỗi: chưa chắc kiểu phần tử là Double.
```

`? extends Number` cam kết rằng các phần tử đọc ra **là `Number` hoặc subtype của `Number`**. Nó không cam kết collection có thể tiếp nhận mọi `Number`: danh sách thực tế có thể là `List<Integer>`, `List<Double>`, v.v.

### 5.1. Không thể gán trực tiếp vào `List<T>`

```java
List<? extends Number> result = readNumbers();

// List<Number> numbers = result; // Lỗi biên dịch.
List<? extends Number> view = result; // Hợp lệ.
```

`List<Number>` cho phép thêm một `Double`, trong khi `List<? extends Number>` không bảo đảm điều đó. Java Generics là **invariant**: `List<Integer>` không phải subtype của `List<Number>`.

Đừng dùng ép kiểu không kiểm tra:

```java
// List<Number> unsafe = (List<Number>) (List<?>) result;
```

Cách ép kiểu này có thể làm mất tính an toàn và khiến caller thêm đối tượng sai loại vào danh sách do thư viện sở hữu.

### 5.2. Có thể sao chép sang một `List<T>` mới

Nếu caller cần một danh sách `List<Number>` có khả năng nhận thêm các loại `Number`, hãy **sao chép phần tử**:

```java
List<? extends Number> source = readNumbers();
List<Number> numbers = new ArrayList<>(source);

numbers.add(3.14); // Hợp lệ vì kiểu đích thực sự là List<Number>.
```

Phương thức khởi tạo `ArrayList(Collection<? extends E>)` được thiết kế chính để chấp nhận nguồn có kiểu phần tử con của `E`. Bản sao và danh sách nguồn có cấu trúc riêng; thêm phần tử vào bản sao không thêm vào nguồn.

Tuy nhiên đây là **shallow copy**: phần tử tham chiếu bên trong được chia sẻ, nên việc sửa trạng thái của đối tượng phần tử mutable có thể vẫn ảnh hưởng cả hai phía.

### 5.3. Wildcard cận trên không bảo đảm immutable

```java
List<? extends Number> view = new ArrayList<Integer>();
view.clear(); // Biên dịch và chạy được; danh sách ở đây mutable.
// view.add(123); // Không biên dịch được.
```

Việc compiler ngăn `add(123)` không đồng nghĩa danh sách là bất biến. Tùy implementation, `clear()`, `remove(...)`, `removeIf(...)`, `sort(...)` hoặc các phép thay đổi cấu trúc không cần truyền giá trị phần tử có thể khả thi.

Nếu API muốn cam kết **không được thay đổi** collection, phải dùng hợp đồng và implementation riêng như `List.copyOf(...)`, `List.of(...)` hoặc một wrapper không cho sửa. Wildcard không thay thế cơ chế bất biến.

### 5.4. Mất thông tin subtype cụ thể

Nếu thư viện trả về `List<Dog>` nhưng khai báo công khai `List<? extends Animal>`:

```java
static List<? extends Animal> getAnimals() {
    return List.of(new Dog());
}
```

thì caller không thể mặc định nhận một `Dog`:

```java
Animal animal = getAnimals().get(0); // Hợp lệ.
// Dog dog = getAnimals().get(0);    // Không hợp lệ về kiểu.
```

Ngay cả khi hôm nay implementation chỉ tạo `Dog`, chữ ký cho phép implementation ngày mai trả về `List<Cat>`. Khai báo rộng có thể là mục đích thiết kế, nhưng nếu API **luôn bảo đảm phần tử kiểu `Dog`**, `List<Dog>` thông báo đúng hợp đồng hơn.

## 6. Trả về `List<? super T>`: ghi được T nhưng khó đọc T

Xét:

```java
static List<? super Integer> writableNumbers() {
    return new ArrayList<Number>();
}
```

Ở caller:

```java
List<? super Integer> result = writableNumbers();
result.add(10);                  // Hợp lệ.
result.add(Integer.valueOf(20)); // Hợp lệ.
Object value = result.get(0);    // Hợp lệ.

// Integer x = result.get(0); // Lỗi biên dịch.
// result.add(3.14);          // Lỗi biên dịch.
```

`? super Integer` cho biết kiểu phần tử thực tế có thể là `Integer`, `Number` hoặc `Object`. Nó cho phép thêm `Integer` và subtype của `Integer`, nhưng đọc từ `get` chỉ được bảo đảm là `Object`.

### 6.1. Vì sao `? super T` thường khó hiểu ở API trả về?

Chữ ký:

```java
List<? super Animal> getSink();
```

ngầm nói với caller rằng họ đang nhận một collection có khả năng **tiêu thụ `Animal`**. Điều này có thể đúng nếu API cố ý trả về một vùng đích ghi dữ liệu, nhưng làm mờ các câu hỏi:

- Ai sở hữu danh sách và ai có quyền chỉnh sửa?
- Danh sách có mutable không?
- Caller cần đọc lại các phần tử dưới dạng kiểu nào?
- Tại sao không công khai một hành vi đơn giản hơn như `void addAnimal(Animal item)`?

Ví dụ API ghi thông qua một phương thức thường rõ hơn:

```java
interface AnimalReceiver {
    void addAnimal(Animal animal);
}
```

Đây là đề xuất thiết kế khi API chỉ cung cấp hành động **nhận đối tượng**, không cần công khai cấu trúc `List`. Nó tránh vô tình cho caller quyền gọi những phương thức khác của `List`.

### 6.2. Cận dưới không có nghĩa luôn thêm thành công ở runtime

```java
List<? super Integer> immutable = List.<Number>of(1, 2);
immutable.add(3); // Biên dịch được, nhưng UnsupportedOperationException.
```

`? super T` là lời bảo đảm **an toàn kiểu**, không phải lời bảo đảm implementation hỗ trợ thay đổi. Hợp đồng API cần ghi rõ tính mutable và hành vi khi gọi các thao tác sửa.

## 7. Wildcard ở kiểu trả về có thể lan truyền qua nhiều lớp gọi

Giả sử một thư viện khai báo:

```java
static List<? extends Animal> findAnimals() {
    return List.of(new Dog());
}
```

Ứng dụng có thể chỉ đọc:

```java
static void printAnimals(List<? extends Animal> values) {
    for (Animal value : values) {
        System.out.println(value);
    }
}

printAnimals(findAnimals()); // Hợp lệ.
```

Nhưng nếu một hàm downstream yêu cầu `List<Animal>`:

```java
static void appendCat(List<Animal> values) {
    values.add(new Cat());
}

// appendCat(findAnimals()); // Lỗi biên dịch.
```

Caller phải đổi thiết kế, ví dụ sao chép:

```java
List<Animal> copied = new ArrayList<>(findAnimals());
appendCat(copied);
```

Trong ví dụ này, `appendCat` là một đoạn phương thức minh họa đặt trong cùng class, không phải một chương trình độc lập.

Khi nhiều tầng xử lý liên tục truyền `List<? extends Animal>`, wildcard có thể “lan” sang chữ ký của các phương thức trung gian. Điều đó vẫn **đúng về kiểu** nếu mọi tầng chỉ đọc. Vấn đề xuất hiện khi tầng tiếp theo cần một kiểu chính xác hơn, cần ghi hoặc cần mô tả quan hệ giữa nhiều giá trị.

### 7.1. Không được thu hẹp wildcard dựa trên suy đoán

```java
List<? extends Animal> values = findAnimals();
// List<Dog> dogs = values; // Lỗi biên dịch.
```

Không phải mọi `List<? extends Animal>` đều là `List<Dog>`. Nếu cần `Dog`, phải để API đảm bảo `Dog` ngay từ chữ ký hoặc dùng bộ lọc và kiểm tra runtime thích hợp.

## 8. Thiết kế API thay thế: trả về kiểu cụ thể khi có bảo đảm cụ thể

Nếu API quản lý danh sách `Dog` và hợp đồng bảo đảm kết quả là danh sách các `Dog`, hãy trả về:

```java
static List<Dog> findDogs() {
    return List.of(new Dog());
}
```

Caller nhận đúng thông tin:

```java
List<Dog> dogs = findDogs();
Dog first = dogs.get(0);
```

Đây là lựa chọn đơn giản khi subtype thực sự là một phần của hợp đồng.

**Độ cụ thể không nhất thiết là cấp class triển khai**: bạn vẫn có thể trả về interface `List<Dog>`, `Collection<Dog>` hoặc `Iterable<Dog>`, tùy phương thức mà caller cần. Điều nên rõ là **đối số kiểu phần tử** và hợp đồng sử dụng, không phải bắt caller biết implementation `ArrayList`.

### 8.1. Trả về `List<Animal>` bằng cách tạo bản sao

Nếu API chủ động muốn công khai phần tử dưới dạng `Animal` và cho caller nhận được `List<Animal>`, trong khi dữ liệu gốc là `List<Dog>`, có thể tạo bản sao:

```java
static List<Animal> animalSnapshot(List<Dog> dogs) {
    return new ArrayList<>(dogs);
}
```

`new ArrayList<>(dogs)` xây một `List<Animal>` mới. Nó tách cấu trúc danh sách khỏi danh sách nguồn, nhưng không sao chép sâu các đối tượng `Dog`.

Nếu muốn cung cấp **snapshot không cho sửa**:

```java
static List<Animal> immutableAnimalSnapshot(List<Dog> dogs) {
    return List.copyOf(dogs);
}
```

Việc suy luận type parameter của `List.copyOf` có thể dùng kiểu đích `List<Animal>`. Cần lưu ý `List.copyOf` không chấp nhận phần tử `null`. Không nên quảng bá bản sao là deep copy.

### 8.2. Khi API muốn cho phép thêm, vẫn cần nêu ownership

Trả về `List<Animal>` giúp caller có thể viết `result.add(new Cat())` **về mặt kiểu**; nhưng kết quả có thực sự mutable hay không phụ thuộc implementation. Ví dụ `List.copyOf` trả về danh sách không thể sửa dù kiểu khai báo là `List<Animal>`.

Nên ghi rõ trong hợp đồng API: đây là snapshot bất biến, bản sao mutable do caller sở hữu, hay view dựa trên dữ liệu nội bộ có thể thay đổi theo thời gian. Những lựa chọn đó độc lập với wildcard.

## 9. Thiết kế API thay thế: phương thức generic giữ quan hệ kiểu

Khi người gọi cung cấp thông tin kiểu cần thiết, API có thể dùng một **type parameter có tên** để liên kết đầu vào và đầu ra:

```java
static <T extends Animal> List<T> onlyType(
        List<? extends Animal> source,
        Class<T> requestedType) {

    List<T> result = new ArrayList<>();
    for (Animal animal : source) {
        if (requestedType.isInstance(animal)) {
            result.add(requestedType.cast(animal));
        }
    }
    return result;
}
```

Cách dùng:

```java
List<Animal> source = List.of(new Dog(), new Cat());
List<Dog> dogs = onlyType(source, Dog.class);
Dog firstDog = dogs.get(0);
```

`Class<T>` cung cấp **căn cứ kiểm tra ở runtime** trước khi trả về `List<T>`. Java có thể chứng minh các phần tử trong kết quả đều thuộc `T`, thay vì bắt caller làm unchecked cast.

Đoạn này là mã minh họa đặt trong class với `import java.util.*;`.

### 9.1. Không khai báo type parameter giả tạo để chiều ý caller

Cẩn thận với một API kiểu:

```java
// Ví dụ chữ ký nguy hiểm nếu không có ràng buộc thực:
// static <T extends Animal> List<T> findAllAnimals() { ... }
```

Nếu lời gọi cho phép caller tự ý suy luận `T = Dog` hoặc `T = Cat`, trong khi dữ liệu thực tế có thể chứa cả hai, implementation không có cách an toàn để đáp ứng lời hứa đó chỉ từ tên `T` do caller chọn.

Một generic return type `List<T>` chỉ đúng khi có quan hệ kiểu được bảo đảm: đối số `Class<T>`, tham số đầu vào `List<T>`, một container `Repository<T>` có kiểu cố định, hoặc cơ chế lưu trữ/kiểm tra tương đương.

Không thay wildcard bằng `<T>` chỉ để ép mã biên dịch; phải bảo toàn tính đúng đắn của hợp đồng.

## 10. Thiết kế API thay thế: gắn tham số kiểu với đối tượng sở hữu

Một repository generic có thể xác định loại phần tử ở **thời điểm tạo đối tượng**:

```java
interface Repository<T> {
    List<T> findAll();
}
```

Sau đó:

```java
Repository<Dog> dogRepository = /* một implementation Repository<Dog> */;
List<Dog> dogs = dogRepository.findAll();
```

Ví dụ sử dụng ở trên chỉ minh họa quan hệ kiểu và chưa có implementation cụ thể. Ưu điểm là `T` được liên kết với repository, nên phương thức `findAll()` có thể trả về `List<T>` mà không cần `List<? extends T>`.

Nếu cần không cho caller sửa danh sách, implementation có thể trả `List.copyOf(stored)` hoặc một collection bất biến được mô tả rõ. Kiểu `List<T>` vẫn giữ thông tin kiểu chính xác.

## 11. Khi wildcard return là một chủ ý tốt

Không phải mọi wildcard return đều là “mùi thiết kế”.

### 11.1. Muốn công khai một view chỉ bảo đảm cận trên

Một API tổng hợp dữ liệu từ nhiều nguồn có thể không thể cam kết kiểu phần tử chính xác hơn `Animal`:

```java
static List<? extends Animal> animalsFromSource(boolean dogsOnly) {
    return dogsOnly
            ? List.of(new Dog())
            : List.of(new Cat());
}
```

Ở caller, bảo đảm “đọc được `Animal`” có thể là đủ. `List<? extends Animal>` có thể phản ánh đúng sự không xác định trong contract; nó cũng giữ khả năng implementation trả về collection có kiểu `Dog` hoặc `Cat` mà không sao chép cấu trúc.

Tuy nhiên, nếu **chỉ** muốn caller đọc dưới dạng `Animal`, vẫn có thể cân nhắc `List<Animal>` bằng cách tạo danh sách phù hợp. Lựa chọn phụ thuộc ownership, chi phí sao chép, độ linh hoạt và khả năng thao tác của caller.

### 11.2. Muốn trả về cấu trúc dữ liệu không biết kiểu phần tử

Một API chẩn đoán hoặc khám phá có thể thật sự chỉ bảo đảm `List<?>`:

```java
interface DiagnosticProvider {
    List<?> rawObservations();
}
```

Caller chủ yếu quan tâm số lượng, trình bày và introspection, không kỳ vọng mọi phần tử đều có một kiểu thống nhất ngoài `Object`. Lúc này wildcard nói đúng sự bất định của dữ liệu.

### 11.3. Muốn công khai mục tiêu ghi dữ liệu

Một API rất chuyên biệt có thể trả về `Collection<? super Event>` để người gọi thêm các sự kiện:

```java
interface EventBuffer {
    Collection<? super Event> writableTarget();
}

class Event {}
```

Chữ ký như vậy mô tả **khả năng chấp nhận `Event`**, nhưng cần documentation về mutability, ownership, đồng bộ hóa, tác dụng phụ, thứ tự và cách xử lý lỗi. Nếu nhiệm vụ thật sự chỉ là ghi sự kiện, một phương thức `append(Event event)` thường rõ ràng hơn việc trao ra toàn bộ `Collection`.

## 12. Chương trình Java 17+ hoàn chỉnh

Lưu thành **`WildcardReturnApiDemo.java`**. Chương trình so sánh chữ ký trả về wildcard, kiểu chính xác, snapshot theo kiểu cha và generic method trả kết quả có kiểu được kiểm chứng.

```java
import java.util.ArrayList;
import java.util.List;

public class WildcardReturnApiDemo {
    static class Animal {
        private final String name;

        Animal(String name) {
            this.name = name;
        }

        @Override
        public String toString() {
            return getClass().getSimpleName() + "(" + name + ")";
        }
    }

    static final class Dog extends Animal {
        Dog(String name) {
            super(name);
        }
    }

    static final class Cat extends Animal {
        Cat(String name) {
            super(name);
        }
    }

    static List<Dog> findDogs() {
        return List.of(new Dog("Rex"), new Dog("Bolt"));
    }

    static List<? extends Animal> findAnimalsWildcard() {
        return findDogs();
    }

    static List<Animal> animalSnapshot() {
        return new ArrayList<>(findDogs());
    }

    static <T extends Animal> List<T> filterByClass(
            List<? extends Animal> source,
            Class<T> requestedType) {

        List<T> result = new ArrayList<>();
        for (Animal animal : source) {
            if (requestedType.isInstance(animal)) {
                result.add(requestedType.cast(animal));
            }
        }
        return List.copyOf(result);
    }

    public static void main(String[] args) {
        List<? extends Animal> wildcard = findAnimalsWildcard();
        Animal firstAnimal = wildcard.get(0);
        // wildcard.add(new Dog("Max")); // Lỗi biên dịch.

        List<Dog> typed = findDogs();
        Dog firstDog = typed.get(0);

        List<Animal> snapshot = animalSnapshot();
        snapshot.add(new Cat("Mia"));

        List<Animal> mixed = List.of(
                new Dog("Rex"),
                new Cat("Luna"),
                new Dog("Bolt")
        );
        List<Dog> filtered = filterByClass(mixed, Dog.class);

        List<Object> storage = new ArrayList<>();
        List<? super Animal> writableView = storage;
        writableView.add(new Cat("Coco"));
        Object fromWritable = writableView.get(0);

        System.out.println("wildcard=" + firstAnimal);
        System.out.println("typed=" + firstDog);
        System.out.println("snapshot=" + snapshot);
        System.out.println("filtered=" + filtered);
        System.out.println("super-read=" + fromWritable);
    }
}
```

Biên dịch và chạy:

```bash
javac WildcardReturnApiDemo.java
java WildcardReturnApiDemo
```

Stdout:

```text
wildcard=Dog(Rex)
typed=Dog(Rex)
snapshot=[Dog(Rex), Dog(Bolt), Cat(Mia)]
filtered=[Dog(Rex), Dog(Bolt)]
super-read=Cat(Coco)
```

Giải thích các điểm cần kiểm chứng:

1. `findAnimalsWildcard()` công khai `List<? extends Animal>`; caller đọc được `Animal` nhưng không thể thêm tùy ý.
2. `findDogs()` công khai `List<Dog>`, nên caller nhận trực tiếp `Dog` từ `get`.
3. `animalSnapshot()` sao chép sang `List<Animal>`; caller có thể thêm `Cat` vào **bản sao** vì `ArrayList` mutable.
4. `filterByClass(..., Dog.class)` trả `List<Dog>` nhờ kiểm tra `isInstance` và `cast`, không thực hiện unchecked cast.
5. `List<? super Animal>` hỗ trợ thêm `Cat` vì `Cat <: Animal`, nhưng kết quả `get` chỉ được đảm bảo có kiểu `Object`.

Các `List.of(...)` trong chương trình là danh sách không sửa được. Bản sao `new ArrayList<>(...)` có thể sửa. Cả hai trạng thái tồn tại độc lập với wildcard trong chữ ký.

## 13. Wildcard capture có thể phát sinh ở phía caller

Một hạn chế khác khi trả về `List<?>`: kiểu phần tử tuy không biết cụ thể nhưng **vẫn có một kiểu nhất quán** bên trong từng danh sách.

Ví dụ:

```java
static void swapFirstTwo(List<?> items) {
    swapCaptured(items);
}

private static <T> void swapCaptured(List<T> items) {
    if (items.size() >= 2) {
        T first = items.get(0);
        items.set(0, items.get(1));
        items.set(1, first);
    }
}
```

Phương thức `swapCaptured` dùng một type parameter `T` để giữ quan hệ giữa phần tử đọc ra và phần tử ghi lại. Compiler có thể **capture** wildcard của tham số `List<?>` khi gọi helper. Đây là các đoạn method minh họa đặt bên trong một class với `import java.util.List;`.

Điều cần phân biệt:

- `items.add(new Dog())` trên `List<?>` không an toàn vì `?` có thể là một kiểu không liên quan.
- Hoán đổi hai phần tử **của chính cùng một `List<T>`** là an toàn về kiểu: lấy một `T` ra rồi ghi lại vị trí khác cũng yêu cầu `T`.

Phép `set` có thể ném `UnsupportedOperationException` nếu danh sách không cho phép thay đổi. Nếu API trả về wildcard nhưng caller liên tục phải viết helper chỉ để dùng dữ liệu thông thường, cần cân nhắc lại kiểu trả về.

## 14. Tác động đến suy luận generic và quá tải phương thức

### 14.1. Generic method có thể nhận nguồn wildcard mà không cần ép kiểu

```java
static <T> void copyTo(List<? super T> target, List<? extends T> source) {
    target.addAll(source);
}
```

Caller có thể viết:

```java
List<? extends Number> source = List.of(1, 2);
List<Number> target = new ArrayList<>();

copyTo(target, source);
```

Đoạn này nằm trong class với `import java.util.*;`. `copyTo` cho compiler một type parameter `T` để liên kết hai tham số. Kỹ thuật này hữu ích khi không đổi được API đã trả về wildcard; nó **không** biến nguồn thành `List<Number>`.

### 14.2. Không định nghĩa overload chỉ khác generic wildcard

Không được viết hai overload chỉ khác nhau bởi đối số kiểu bên trong `List` như:

```java
// void inspect(List<? extends Number> values) {}
// void inspect(List<? super Integer> values) {}
```

Hai chữ ký sẽ bị xung đột do **type erasure**: cả hai có cùng dạng tham số raw `List` ở bytecode. Nếu API cần hai hành vi, đặt hai tên có nghĩa riêng hoặc thay đổi tham số sao cho có chữ ký khác thật sự.

Vấn đề erasure áp dụng cho generic parameter nói chung; wildcard return không tạo ra một cơ chế overload đặc biệt.

## 15. Bảng lựa chọn chữ ký API

| Nhu cầu của caller | Chữ ký thường phù hợp | Lý do |
| --- | --- | --- |
| API luôn trả các `Dog` | `List<Dog> findDogs()` | Caller đọc trực tiếp `Dog`, không mất thông tin subtype |
| API công khai các phần tử dưới dạng `Animal` và muốn trả một danh sách có kiểu cố định | `List<Animal> findAnimals()` | Không lan wildcard; phải xây/trả một `List<Animal>` thực sự |
| API chỉ cam kết phần tử là subtype của `Animal` và muốn trả view không phải copy | `List<? extends Animal> findAnimals()` | Giữ độ linh hoạt subtype; caller chủ yếu đọc |
| API không thể cam kết kiểu phần tử cụ thể | `List<?> inspect()` | Caller phải xử lý phần tử như `Object` |
| Caller yêu cầu một subtype và API kiểm chứng được | `<T extends Animal> List<T> find(Class<T> type)` | `T` được ràng buộc qua thông tin đầu vào và kiểm tra thực tế |
| Loại phần tử gắn với repository | `Repository<T>.findAll(): List<T>` | Kiểu `T` được xác định khi tạo repository |
| Caller chỉ cần gửi thêm dữ liệu | `void append(Animal value)` | Công khai hành vi, không lộ collection nội bộ |
| API cố ý đưa ra đích ghi tổng quát | `Collection<? super Animal> writableTarget()` | Cho phép `add(Animal)`, nhưng đọc chỉ bảo đảm `Object` |

Bảng là hướng dẫn lựa chọn, không phải quy tắc một chữ ký cho mọi API. Còn cần xét mutability, null, ownership, hiệu năng sao chép, độ ổn định của hợp đồng và khả năng phát triển API.

## 16. Những hiểu lầm và lỗi thường gặp

### Sai lầm 1: “Trả về wildcard luôn là sai”

Wildcard return là cú pháp hợp lệ và có thể diễn đạt chính xác sự bất định mà API cố ý công khai. Vấn đề là caller có thực sự cần tự xử lý wildcard và các giới hạn kéo theo hay không.

### Sai lầm 2: “`? extends T` làm collection trở thành read-only”

`? extends T` hạn chế **ghi giá trị mới thuộc kiểu không biết** vào collection. Nó không ngăn toàn bộ thao tác sửa như `clear()`; không bảo đảm snapshot, immutable hay thread-safe.

### Sai lầm 3: “Có thể gán kết quả `List<? extends T>` cho `List<T>`”

Generic không tự động biến thiên theo quan hệ subtype của phần tử. Nếu cần `List<T>` riêng, hãy sao chép hoặc thiết kế API trả `List<T>` ngay từ đầu.

### Sai lầm 4: “`List<? super T>` trả về là `List<T>` có thể đọc T”

Không. Kiểu phần tử thực tế có thể là supertype của `T`; kết quả `get` chỉ được bảo đảm là `Object`.

### Sai lầm 5: “Đổi sang `<T> List<T>` là sửa được mọi vấn đề”

Nếu không có nguồn ràng buộc/kiểm chứng `T`, phương thức không thể an toàn hứa rằng dữ liệu thực tế hợp mọi kiểu do caller chọn. Đừng dùng unchecked cast để biến một API sai thành API “trông có vẻ generic”.

### Sai lầm 6: “Trả `List<T>` nghĩa là caller có thể sửa”

Chữ ký `List<T>` cho phép `add(T)` ở compile-time, nhưng implementation có thể trả `List.of`, `List.copyOf` hoặc wrapper unmodifiable. Quyền sửa phải được hợp đồng API xác định.

### Sai lầm 7: “Dùng `Object` hoặc raw `List` để loại wildcard là cải tiến”

`List<Object>` không thể thay thế tùy ý cho `List<String>` bởi invariance. Raw `List` làm suy yếu kiểm tra kiểu. Nếu dữ liệu thật sự không biết kiểu, `List<?>` có thể là cách diễn đạt an toàn nhất.

## 17. Bài tập tự đánh giá

Cho:

```java
class Vehicle {}
class Car extends Vehicle {}
class Bike extends Vehicle {}

static List<? extends Vehicle> loadVehicles() {
    return List.of(new Car(), new Bike());
}
```

### Bài 1. Phép gán nào hợp lệ?

```java
List<? extends Vehicle> a = loadVehicles(); // (1)
// List<Vehicle> b = loadVehicles();         // (2)
Vehicle c = loadVehicles().get(0);          // (3)
// Car d = loadVehicles().get(0);           // (4)
```

**Đáp án:** (1), (3) hợp lệ; (2) sai vì không thể thu hẹp wildcard về `List<Vehicle>`; (4) sai vì kết quả đọc chỉ được bảo đảm là `Vehicle`, có thể là `Bike`.

### Bài 2. Có thể thêm `Car` vào kết quả không?

```java
List<? extends Vehicle> vehicles = loadVehicles();
// vehicles.add(new Car()); // (1)
```

**Đáp án:** Không. Kiểu phần tử thực tế có thể là `Car`, `Bike` hoặc `Vehicle`. Nếu caller cần cấu trúc có thể thêm `Vehicle`, sao chép:

```java
List<Vehicle> editable = new ArrayList<>(vehicles);
editable.add(new Car());
```

### Bài 3. Khi nào nên trả `List<Car>`?

Một phương thức `loadCars()` luôn chỉ trả các `Car`, và caller cần thao tác dựa trên kiểu `Car`. Chọn `List<Car>`, vì nó thể hiện đúng hợp đồng. Nếu API cố ý che subtype nhằm chỉ công khai `Vehicle`, cần đánh giá lý do và những giới hạn phát sinh trước khi dùng `List<? extends Vehicle>`.

### Bài 4. Hãy chỉ ra nguy cơ của chữ ký này

```java
// static <T extends Vehicle> List<T> loadAll() { ... }
```

Nếu dữ liệu thực tế chứa `Car` và `Bike`, caller có thể mong `List<Car>` mà implementation không bảo đảm được. Cần thêm bộ lọc có kiểm chứng như `Class<T>`, hoặc chuyển sang `List<Vehicle>`/mô hình repository có kiểu ràng buộc.

### Bài 5. Tìm chữ ký phù hợp cho nơi nhận dữ liệu

Một API muốn caller gửi `Vehicle` nhưng không yêu cầu caller đọc collection nội bộ. Nên cung cấp:

```java
void addVehicle(Vehicle vehicle);
```

Nó bộc lộ hành vi cần thiết và không ràng buộc caller với cấu trúc lưu trữ `List`. Trong nội bộ implementation vẫn có thể dùng `Collection<? super Vehicle>` làm consumer.

## 18. Checklist khi review chữ ký trả về

1. **Caller cần biết chính xác kiểu phần tử nào?** Nếu có bảo đảm rõ ràng, cân nhắc `List<T>` cụ thể.
2. **Caller chỉ đọc hay cũng cần ghi?** Với `? extends T`, đừng kỳ vọng có thể thêm `T`; với `? super T`, đừng kỳ vọng đọc ra `T`.
3. **Wildcard có truyền tiếp qua nhiều tầng code không?** Nếu người dùng phải liên tục cast/copy/wrapper, xem lại hợp đồng public.
4. **Có cần giữ subtype chính xác không?** Khi có, trả `List<Dog>` thay vì vô cớ làm rộng thành `List<? extends Animal>`.
5. **Có nguồn kiểm chứng cho generic return `<T>` không?** Tham số `Class<T>`, đối số `List<T>` hoặc đối tượng sở hữu `Repository<T>` là các mẫu thông thường.
6. **API có trả view hay snapshot?** Nêu rõ dữ liệu có chia sẻ với nội bộ, có đổi theo thời gian hay không, và nếu sao chép thì sao chép nông hay sâu.
7. **Danh sách có mutable không?** Wildcard và mutability độc lập; document rõ khả năng thêm/xóa/sửa và các ngoại lệ runtime.
8. **Có cần trả cả collection không?** Nếu mục tiêu chỉ là nhận dữ liệu, một hành vi `add(T)` có thể là API phù hợp hơn.
9. **Có đang dựa vào unchecked cast/raw type để xóa lỗi không?** Xem lại kiểu gốc; đừng bỏ bảo vệ của compiler.

## 19. Tài liệu đọc thêm

- Oracle Java Tutorials — [Guidelines for Wildcard Use](https://docs.oracle.com/javase/tutorial/java/generics/wildcardGuidelines.html): producer/consumer và lưu ý về wildcard return type.
- Oracle Java Tutorials — [Wildcards and Subtyping](https://docs.oracle.com/javase/tutorial/java/generics/subtyping.html): quan hệ giữa các kiểu generic chứa wildcard.
- Oracle Java Tutorials — [Wildcard Capture and Helper Methods](https://docs.oracle.com/javase/tutorial/java/generics/capture.html): cách xử lý wildcard chưa biết bằng generic helper.
- Java Language Specification 17 — [§4.5.1 Type Arguments of Parameterized Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.5.1): cú pháp, containment và ý nghĩa wildcard.
- Java SE 17 API — [List.copyOf(Collection)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)): snapshot unmodifiable, hành vi null và hợp đồng sao chép.

**Kết luận:** PECS hữu ích nhất khi xác định **hướng dữ liệu của tham số generic**. Với kiểu trả về, mục tiêu là truyền cho caller **đúng và đủ thông tin kiểu** để sử dụng API. Dùng `List<T>` khi `T` được bảo đảm; dùng wildcard khi sự không xác định của kiểu phần tử chính là điều API muốn công khai; và luôn mô tả riêng mutability, ownership và khả năng sao chép.