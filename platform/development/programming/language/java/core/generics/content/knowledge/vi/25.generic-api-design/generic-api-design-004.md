# Dùng wildcard cho đầu vào linh hoạt theo PECS trong thiết kế API Java Generics

## 1. Vấn đề: API nhận được `List<Dog>` nhưng lại từ chối `List<Animal>`

Bạn đang xây một API nhận danh sách động vật:

```java
class Animal {
    String name() {
        return "animal";
    }
}

class Dog extends Animal {
}

class Cat extends Animal {
}
```

Một phiên bản đầu tiên:

```java
static void printNames(List<Animal> animals) {
    for (Animal animal : animals) {
        System.out.println(animal.name());
    }
}
```

Nhưng caller có một biến:

```java
List<Dog> dogs = new ArrayList<>();
```

và gặp lỗi:

```java
// Không biên dịch:
// printNames(dogs);
```

**Nguyên nhân:** Java Generics là *invariant*: dù `Dog extends Animal`, `List<Dog>` không phải subtype của `List<Animal>`.

Nếu method chỉ **đọc** danh sách, buộc caller chuyển đổi/copy sang `List<Animal>` là không cần thiết. Chữ ký linh hoạt hơn:

```java
static void printNames(List<? extends Animal> animals) {
    for (Animal animal : animals) {
        System.out.println(animal.name());
    }
}
```

Bây giờ method có thể nhận `List<Animal>`, `List<Dog>`, `List<Cat>` và các danh sách chứa subtype thích hợp khác, trong khi vẫn đọc mỗi phần tử như `Animal`.

Nếu method có nhiệm vụ **thêm `Dog`** vào một collection, hướng wildcard phải đảo lại:

```java
static void addDefaultDog(List<? super Dog> target) {
    target.add(new Dog());
}
```

Một `List<Dog>`, `List<Animal>` hoặc `List<Object>` đều có thể là đích nhận `Dog`.

Quy tắc nhớ là **PECS — Producer Extends, Consumer Super**:

- **Producer `? extends T`**: nguồn cung cấp đối tượng mà ta có thể đọc như `T`.
- **Consumer `? super T`**: đích tiêu thụ/nhận đối tượng `T` mà ta có thể ghi vào.
- Nếu không cần đọc hoặc ghi kiểu cụ thể, `<?>` có thể đủ.
- Nếu phải vừa đọc vừa ghi theo cùng một kiểu được xác định, một **type parameter `<T>`** hoặc kiểu cụ thể thường thích hợp hơn một wildcard.

Bài này tập trung vào việc chọn **chữ ký phương thức API linh hoạt nhưng an toàn**, không đơn thuần thay `List<T>` bằng wildcard ở mọi vị trí. Các ví dụ hợp lệ và không hợp lệ đã được kiểm tra với Java 17.

## 2. Phân biệt quan hệ subtype của giá trị và của generic container

Một `Dog` là một `Animal`:

```java
Dog dog = new Dog();
Animal animal = dog;
```

Nhưng:

```java
List<Dog> dogs = new ArrayList<>();

// Không hợp lệ:
// List<Animal> animals = dogs;
```

Đây là **invariance** của parameterized types. Cùng quy tắc với `Collection<Dog>`, `Set<Dog>` và nhiều generic types khác.

### 2.1. Vì sao Java không cho gán `List<Dog>` sang `List<Animal>`?

Giả sử gán được:

```java
List<Dog> dogs = new ArrayList<>();
List<Animal> animals = dogs; // Giả sử được phép.
animals.add(new Cat());      // Cat cũng là Animal.
Dog value = dogs.get(0);     // Nhưng slot có thể là Cat!
```

Nếu Java cho phép, đoạn code có thể phá hợp đồng `List<Dog>`: danh sách đã giữ `Cat` nhưng một caller khác tin mỗi phần tử là `Dog`.

Java chặn từ compile time thay vì đợi đến lúc đọc.

### 2.2. Mảng Java khác Generic collections

Mảng tham chiếu trong Java có tính *covariant*:

```java
Dog[] dogs = new Dog[1];
Animal[] animals = dogs;

// Có thể biên dịch, nhưng ném ArrayStoreException:
// animals[0] = new Cat();
```

JVM có runtime component type để chặn phép gán `Cat` vào mảng thật `Dog[]`.

Generic `List<Dog>` thường không có runtime class riêng `List<Dog>` để JVM thực hiện store check theo type argument. Vì vậy Generic invariant giúp ngăn nguy cơ sai kiểu ngay tại source.

**Không suy từ mảng sang Generics.** `Animal[]` và `List<Animal>` có những quy tắc subtype khác nhau.

### 2.3. Wildcard mở linh hoạt nhưng cũng giới hạn thao tác

Một tham số `List<? extends Animal>` nhận được nhiều danh sách con của Animal, đổi lại caller method không được tự thêm bất kỳ `Dog` hay `Cat` tùy ý vào list đó.

Một tham số `List<? super Dog>` nhận được nhiều đích tương thích để thêm Dog, đổi lại khi đọc phần tử, method không thể giả định object nhận về luôn là Dog.

Đây không phải sự bất tiện ngẫu nhiên, mà là **đúng mức bảo đảm kiểu mà chữ ký có thể cung cấp**.

## 3. Producer Extends: đọc dữ liệu với `? extends T`

Xem API:

```java
static String firstName(List<? extends Animal> source) {
    return source.get(0).name();
}
```

Ở nơi gọi:

```java
List<Dog> dogs = List.of(new Dog());
List<Cat> cats = List.of(new Cat());

String fromDogs = firstName(dogs);
String fromCats = firstName(cats);
```

Ở bên trong method:

- `source` có thể thực là `List<Dog>`, `List<Cat>` hoặc `List<Animal>`.
- Bất cứ phần tử nào đọc được đều có thể dùng như `Animal`.
- Method không có quyền biết **kiểu phần tử cụ thể ẩn sau wildcard**.

### 3.1. Đọc dưới dạng bound là an toàn

```java
Animal first = source.get(0);
```

Nếu kiểu phần tử thật là Dog, Dog vẫn là Animal. Nếu kiểu thật là Cat, Cat cũng là Animal. Đọc như Animal giữ đúng hợp đồng chung.

Ngược lại:

```java
// Không biên dịch:
// Dog first = source.get(0);
```

Nếu nguồn thật là List<Cat>, biến Dog sẽ sai. Compiler không cho khẳng định như vậy.

### 3.2. Vì sao không thêm `new Dog()` vào producer?

```java
static void invalid(List<? extends Animal> source) {
    // Không biên dịch:
    // source.add(new Dog());
}
```

Giả sử caller đã truyền `List<Cat>`. Việc thêm Dog vào đó là sai. Compiler mô hình hóa dấu `?` bằng một **capture type** chưa biết, giới hạn trên bởi Animal; không thể chứng minh Dog hợp lệ với mọi capture type có thể có.

Đây là nguyên tắc **Producer Extends**: một nguồn được khai báo nhằm **cung cấp** phần tử, không dùng nó để đưa phần tử có subtype tùy chọn trở lại.

### 3.3. `null` là trường hợp đặc biệt

Về mặt type system, `source.add(null)` có thể được chấp nhận vì null có thể gán cho mọi reference type phù hợp. Nhưng:

- Danh sách có thể không cho phép null.
- Danh sách có thể immutable/unmodifiable.
- Việc thêm null hiếm khi phù hợp mục đích “producer”.

Đừng biến ngoại lệ cú pháp này thành lời khuyên sử dụng. **PECS nói về giá trị khác null và hợp đồng kiểu thông thường**, còn mutability/null policy là các quy tắc riêng.

### 3.4. `? extends` không có nghĩa `List` chỉ đọc vật lý

Một `List<? extends Animal>` có thể tham chiếu tới một `ArrayList<Dog>` mutable. Wildcard chỉ giới hạn **những thao tác kiểu an toàn qua tham chiếu đó**; nó không biến object thành immutable hoặc thread-safe.

Method vẫn có thể gọi các thao tác khác như `clear()` nếu collection cho phép, dù điều đó thường là hành vi bất ngờ đối với một API nguồn. Khi thiết kế một API chỉ đọc, vừa dùng wildcard đúng hướng vừa cam kết không đột biến nguồn theo contract.

## 4. Consumer Super: ghi giá trị với `? super T`

Giả sử bạn có Dog mới và cần đưa vào đích:

```java
static void addDefaultDog(List<? super Dog> target) {
    target.add(new Dog());
}
```

Các loại đích hợp lệ:

```java
List<Dog> dogs = new ArrayList<>();
List<Animal> animals = new ArrayList<>();
List<Object> objects = new ArrayList<>();
```

Cả ba có thể truyền vào phương thức trên:

```java
addDefaultDog(dogs);
addDefaultDog(animals);
addDefaultDog(objects);
```

Vì mọi danh sách đó đều có thể chứa một Dog theo hợp đồng kiểu đã khai báo.

### 4.1. `? super Dog` là một kiểu chưa biết nhưng không hẹp hơn Dog

Trong `List<? super Dog>`, type argument thật có thể là `Dog`, `Animal`, `Object`, hoặc một supertype phù hợp khác của Dog. Bất kể là loại nào, ghi Dog đều an toàn:

```java
target.add(new Dog());
```

Thêm một subtype của Dog (nếu Dog không final) cũng an toàn theo quan hệ subtype.

Nhưng thêm Animal chung hoặc Cat thì không:

```java
// Không an toàn và không biên dịch:
// target.add(new Animal());
// target.add(new Cat());
```

Nếu đích thực là List<Dog>, Animal/Cat không đáp ứng yêu cầu của danh sách.

### 4.2. Đọc từ `? super Dog` chỉ được bảo đảm là Object

```java
Object value = target.get(0);
```

được phép. Nhưng:

```java
// Không biên dịch:
// Dog value = target.get(0);
```

vì đích thực có thể là `List<Object>` và chứa một String, Integer hoặc bất kỳ Object khác từ trước.

**Consumer Super:** người viết method có quyền **đặt Dog vào**, nhưng không thể giả định **mọi phần tử có sẵn** đều là Dog.

### 4.3. Dùng super cho đầu ra có quyền ghi

Tham số đích còn có thể dùng interface tổng quát:

```java
static void addDog(Collection<? super Dog> target) {
    target.add(new Dog());
}
```

Nếu chỉ cần `add`, nhận `Collection` linh hoạt hơn nhận `List`. Caller có thể cung cấp `ArrayList<Animal>`, `HashSet<Animal>` hoặc các implementation `Collection` khác có `add` phù hợp.

**Nguyên tắc thiết kế bổ sung:** nhận interface **hẹp nhất về khả năng method cần**, không phải lúc nào cũng dùng `List` vì quen tay. Nếu cần truy cập theo index, `List` là hợp lý; nếu chỉ thêm, `Collection` thường đủ.

## 5. Bảng quyền đọc và ghi cần nhớ

Xét kiểu `Dog extends Animal`.

| Kiểu tham chiếu | Đọc phần tử an toàn thành | Ghi giá trị khác null có thể chứng minh an toàn |
| --- | --- | --- |
| `List<Dog>` | `Dog` | `Dog` và subtype của Dog |
| `List<Animal>` | `Animal` | `Animal` và subtype của Animal |
| `List<? extends Animal>` | `Animal` | Không ghi tùy ý Dog/Animal |
| `List<? super Dog>` | `Object` | `Dog` và subtype của Dog |
| `List<?>` | `Object` | Không ghi phần tử tùy ý |
| `List<Object>` | `Object` | Bất kỳ Object |

`List<? extends Animal>` không đồng nghĩa `List<Animal>`. Nó có thể tham chiếu tới danh sách Dog/Cat khác nhau.

`List<? super Dog>` cũng không đồng nghĩa `List<Dog>`. Nó có thể tham chiếu tới danh sách Animal hoặc Object.

### 5.1. Giới hạn nào do Generics, giới hạn nào do runtime collection?

Compiler có thể cho gọi `add` nhưng runtime object có thể không sửa được:

```java
List<Dog> fixed = List.of(new Dog());

// Cú pháp Generic hợp lệ, nhưng runtime ném
// UnsupportedOperationException nếu gọi:
fixed.add(new Dog());
```

Tương tự với `Collections.unmodifiableList` hoặc những collection implementation có giới hạn riêng. PECS **không cấp quyền sửa vật lý**; nó kiểm tra tính tương thích kiểu.

## 6. Hai hướng trên cùng một phương thức: copy từ producer sang consumer

Đây là mẫu tiêu biểu nhất của PECS:

```java
static <T> void appendAll(
        List<? extends T> source,
        Collection<? super T> target) {

    for (T item : source) {
        target.add(item);
    }
}
```

`source` là **producer** của T: ta đọc từng phần tử như T.

`target` là **consumer** của T: ta thêm từng phần tử T vào đó.

`<T>` liên kết hai bên để compiler xác minh được mọi phần tử lấy từ source đều hợp lệ cho target.

### 6.1. Caller truyền List<Dog> và List<Animal>

```java
List<Dog> dogs = new ArrayList<>();
List<Animal> animals = new ArrayList<>();

appendAll(dogs, animals);
```

Compiler có thể suy luận type variable `T` thích hợp với quan hệ subtype giữa Dog và Animal. Không cần ép `List<Dog>` thành `List<Animal>`.

### 6.2. Caller cũng có thể truyền List<Dog> và List<Object>

```java
List<Object> objects = new ArrayList<>();
appendAll(dogs, objects);
```

Hợp đồng cho phép vì Object cũng có thể nhận Dog. Điều này thể hiện cách wildcard giữ được sự linh hoạt tại **cả hai** phía.

### 6.3. Vì sao không viết hai tham số đều là `List<T>`?

```java
static <T> void rigid(List<T> source, List<T> target) {
    target.addAll(source);
}
```

Chữ ký này liên kết cả hai List với **cùng type argument T chính xác**. Khi caller có `List<Dog>` và `List<Animal>`, việc suy luận chung T bị hạn chế bởi invariance.

Chữ ký PECS:

```java
static <T> void flexible(
        List<? extends T> source,
        List<? super T> target) {
    target.addAll(source);
}
```

diễn đạt rõ quan hệ producer/consumer, nên linh hoạt hơn và an toàn.

### 6.4. Lưu ý về tên `append` so với `copy`

`appendAll` ở ví dụ **thêm** các phần tử vào cuối `Collection`. Nó có thể làm kích thước đích tăng.

Trong JDK, `Collections.copy` là một API khác: nó **ghi đè** các vị trí đã tồn tại trong danh sách đích, không tự nới danh sách để append. Đừng nhầm hai semantics khi đọc code.

### 6.5. Side effect và aliasing cần có trong contract

Nếu `source` và `target` trỏ tới cùng mutable collection, một vòng lặp `for-each` vừa duyệt vừa thêm có thể dẫn tới `ConcurrentModificationException` hoặc hành vi không mong đợi. Chữ ký PECS chỉ bảo đảm kiểu, không giải quyết aliasing.

Khi thiết kế API, hãy xác định có cho `source == target` hay không. Nếu muốn hỗ trợ, có thể tạo snapshot nguồn trước hoặc dùng thuật toán phù hợp, đồng thời cân nhắc chi phí bộ nhớ.

## 7. Ví dụ JDK: `Collections.copy` đã dùng PECS

Java 17 khai báo method tương đương:

```java
public static <T> void copy(
        List<? super T> dest,
        List<? extends T> src)
```

Tại đây:

- `src` (*source*) là producer, nên `? extends T`.
- `dest` (*destination*) là consumer, nên `? super T`.

Ví dụ:

```java
List<Integer> numbers =
        new ArrayList<>(List.of(3, 7));

List<Number> target =
        new ArrayList<>(List.of(0, 0, 0));

Collections.copy(target, numbers);
System.out.println(target); // [3, 7, 0]
```

`Collections.copy` thay các phần tử đích ở index tương ứng. **Điều kiện:** danh sách đích phải có kích thước ít nhất bằng danh sách nguồn. `new ArrayList<>(capacity)` chỉ đặt capacity, **không tạo sẵn các phần tử**, nên không thể dùng như một đích có kích thước đủ cho `Collections.copy`.

### 7.1. Khi muốn thêm thay vì ghi đè

Dùng:

```java
target.addAll(numbers);
```

hoặc một API `appendAll` rõ nghĩa.

Chữ ký instance method của `Collection<E>`:

```java
boolean addAll(Collection<? extends E> collection)
```

dùng wildcard `extends` ở **đối số nguồn**. Collection hiện tại đóng vai trò consumer của E; collection được truyền vào cung cấp các phần tử là E hoặc subtype.

### 7.2. Vì sao `Collections.copy` có type parameter T?

T liên kết **nguồn** và **đích**. Nếu chỉ có hai wildcard độc lập không ràng buộc như:

```java
// Không diễn đạt đủ quan hệ giữa hai loại:
// void copy(List<?> target, List<?> source)
```

thì compiler không thể an toàn lấy một object chưa biết kiểu từ source rồi ghi vào target chưa biết kiểu.

**Điểm mấu chốt:** PECS thường kết hợp wildcard **với một `<T>` liên kết hai tham số**, không phải loại bỏ type parameter.

## 8. Generic method để ghép nhiều nguồn có subtype khác nhau

Giả sử bạn muốn ghép danh sách Dog và Cat thành một danh sách Animal mới:

```java
static <T> List<T> concat(
        List<? extends T> left,
        List<? extends T> right) {

    List<T> result = new ArrayList<>(
            left.size() + right.size());
    result.addAll(left);
    result.addAll(right);
    return result;
}
```

Call:

```java
List<Dog> dogs = List.of(new Dog());
List<Cat> cats = List.of(new Cat());

List<Animal> combined = concat(dogs, cats);
```

Cả hai nguồn là producer của các subtype phù hợp với T; T được suy luận từ arguments và target type để tạo kết quả `List<Animal>`.

### 8.1. Vì sao kết quả nên là `List<T>`?

Method **tự tạo** một danh sách mới mà nó sở hữu. Nó biết đã chỉ thêm các giá trị phù hợp với T, nên có thể trả `List<T>`; caller sẽ dùng kết quả theo contract rõ ràng.

Trả `List<? extends T>` ở đây có thể khiến caller khó thêm phần tử T vào kết quả mà không mang lại lợi ích tương ứng. **Wildcard thường hữu ích ở vị trí tham số đầu vào**; kiểu trả về quá nhiều wildcard có thể làm API khó sử dụng.

### 8.2. Tránh che quan hệ kiểu sau khi gộp

```java
List<? extends Animal> combined = concat(dogs, cats);
```

có thể dùng nếu chỉ đọc, nhưng caller sau đó không được thêm Dog vào qua tham chiếu `? extends Animal`. Nếu method thật sự tạo một `List<Animal>` mới cho caller thao tác, khai báo:

```java
List<Animal> combined = concat(dogs, cats);
```

thường thể hiện ý định tốt hơn.

### 8.3. Kiểm tra mutable/immutable

`new ArrayList<>()` tạo một result có thể sửa. Nếu API hứa immutable snapshot, bạn có thể trả `List.copyOf(result)` khi dữ liệu không chứa null và contract phù hợp. `List.copyOf` có những giới hạn riêng như không chấp nhận null; việc “đổi sang unmodifiable” không nên làm mà không xét nghiệp vụ.

## 9. PECS trong `Function`, `Comparator` và những API khác

PECS không chỉ áp dụng cho danh sách. Nó còn xuất hiện trong các functional interfaces.

### 9.1. `Function<? super T, ? extends R>`

Xét generic transform:

```java
static <T, R> void transformAll(
        Iterable<? extends T> source,
        Function<? super T, ? extends R> mapper,
        Collection<? super R> target) {

    for (T item : source) {
        target.add(mapper.apply(item));
    }
}
```

Mỗi thành phần có một vai trò:

- `Iterable<? extends T> source`: nguồn cung cấp T.
- `Function<? super T, ? extends R> mapper`: **tiêu thụ** một T, **tạo ra** R.
- `Collection<? super R> target`: đích nhận R.

Đây là PECS nhìn ở nhiều lớp của một lời gọi.

Ví dụ:

```java
Function<Animal, String> names = Animal::name;

List<Dog> dogs = new ArrayList<>();
List<String> result = new ArrayList<>();

transformAll(dogs, names, result);
```

Dù mapper nhận `Animal`, nó xử lý Dog vì Dog là subtype của Animal. `? super T` trên input của Function thể hiện chính sự linh hoạt này.

### 9.2. Vì sao result của Function là `? extends R`?

Nếu một mapper trả subtype của R, caller vẫn có thể dùng giá trị đó như R. Wildcard `extends` ở **đầu ra** diễn đạt hành vi producer.

Ví dụ kiểu tưởng tượng: một `Function<Animal, Dog>` tạo Dog; nơi cần `Function<? super Animal, ? extends Animal>` có thể chấp nhận khi các ràng buộc tương thích. R được dùng làm kiểu chung của dữ liệu kết quả.

Đừng đảo thành `Function<? extends T, ? super R>` khi muốn tiêu thụ T và trả R: đầu vào `? extends T` có thể quá hẹp để nhận mọi T; đầu ra `? super R` có thể trả kiểu rộng hơn R, làm mất bảo đảm kết quả là R.

### 9.3. `Comparator<? super T>`

`List<E>.sort` có chữ ký:

```java
void sort(Comparator<? super E> comparator)
```

Với `List<Dog>`, bạn có thể sử dụng một `Comparator<Animal>` vì Comparator nhận các Dog như Animal.

```java
Comparator<Animal> byName =
        Comparator.comparing(Animal::name);

List<Dog> dogs = new ArrayList<>();
dogs.sort(byName);
```

Comparator là **consumer của đối tượng cần so sánh**: nó nhận hai E và tính thứ tự, nên `? super E` là hướng hợp lý.

### 9.4. `Comparable<? super T>` trong API chuẩn

JDK còn dùng kiểu:

```java
<T extends Comparable<? super T>>
```

trong những API như `Collections.max(Collection<? extends T>)`. Điều này cho phép một T được so sánh thông qua Comparable của T **hoặc của supertype phù hợp**.

Đây là ví dụ kết hợp:

- Bound của **type variable T**.
- Wildcard `? super T` ở interface tiêu thụ đối tượng để so sánh.
- `Collection<? extends T>` là nguồn giá trị để chọn phần tử lớn nhất.

Không nhất thiết phải học thuộc mọi chữ ký JDK, nhưng việc đọc API này giúp bạn nhìn ra PECS xuất hiện ở những nơi ngoài `List`.

## 10. `List<?>` khi không cần biết kiểu phần tử

Một API chỉ đếm phần tử:

```java
static int count(List<?> items) {
    return items.size();
}
```

không cần `<T>` vì method không liên kết loại phần tử với return value hoặc tham số khác.

`List<?>` tương đương “list của **một loại nào đó chưa biết**”, không phải “list của Object”:

```java
List<String> words = List.of("Java");
List<?> any = words; // Hợp lệ.

// Không hợp lệ:
// List<Object> objects = words;
```

### 10.1. Đọc qua `List<?>`

```java
Object first = any.get(0);
```

hợp lệ. Nhưng compiler không hứa `String` chỉ từ kiểu tĩnh List<?>.

### 10.2. Không thêm tùy ý vào `List<?>`

```java
// Không biên dịch:
// any.add("new");
```

Vì kiểu phần tử thật có thể là Integer, Dog, Cat hoặc loại khác. Dấu `?` không có bound cụ thể để chứng minh String có thể được thêm.

### 10.3. Khi nào `<T>` không tốt hơn `<?>`?

Một chữ ký:

```java
static <T> int countGeneric(List<T> items) {
    return items.size();
}
```

vẫn có thể hợp lệ, nhưng T không đem lại thông tin quan hệ mới. Khi method chỉ quan sát kích thước hoặc in đối tượng dưới dạng Object, `List<?>` thường đơn giản và chính xác hơn.

**Mẹo thiết kế:** chỉ khai báo type parameter khi **tên T cần liên kết ít nhất hai vị trí có ý nghĩa**, hoặc phục vụ bound/return type/constraint. Đây là heuristic, không phải cú pháp bắt buộc của Java.

## 11. Wildcard capture: khi compiler đặt tên cho dấu `?`

Một số thao tác an toàn với *cùng một danh sách* vẫn khó diễn đạt trực tiếp bằng `List<?>`.

Ví dụ muốn đổi chỗ hai phần tử của list, giữ nguyên kiểu thật của chúng:

```java
static void swapFirstTwo(List<?> items) {
    swapCaptured(items);
}

private static <T> void swapCaptured(List<T> items) {
    T first = items.get(0);
    items.set(0, items.get(1));
    items.set(1, first);
}
```

`swapCaptured` dùng một type parameter T để thể hiện rằng cả hai phần tử được đọc/ghi **trên cùng danh sách có cùng captured type**.

### 11.1. Vì sao không tự thêm đối tượng tùy ý?

Helper chỉ lấy giá trị đang thuộc list rồi ghi lại vào cùng list. Nó **không đưa một Dog bên ngoài vào List<?> có thể thật là List<Cat>**.

Đây là trường hợp wildcard capture giúp diễn đạt một thao tác an toàn mà `?` trần không cho compiler biết cách nối thông tin “cùng kiểu” giữa hai lệnh đọc/ghi.

### 11.2. Wildcard capture không vượt qua giới hạn subtype

```java
static void unsafe(List<?> items) {
    // items.add(new Dog()); // Vẫn không hợp lệ.
}
```

Việc bổ sung helper không cho phép tùy tiện thêm một object khác kiểu thực. Type variable trong helper chỉ đặt tên cho một kiểu chưa biết và giữ quan hệ đó nhất quán.

### 11.3. Cần mutable List và đủ phần tử

`swapCaptured` có thể ném `IndexOutOfBoundsException` nếu list ít hơn hai phần tử, hoặc `UnsupportedOperationException` nếu list không cho sửa.

PECS/capture giải quyết bài toán **kiểu tĩnh**, không kiểm tra length hoặc mutability. API production có thể kiểm tra `size() >= 2` và tài liệu hóa yêu cầu mutable.

## 12. Khi nào **không** dùng wildcard?

PECS là hướng dẫn cho phương thức **nhận** dữ liệu; lạm dụng wildcard ở mọi vị trí làm API kém rõ.

### 12.1. Phải vừa đọc vừa ghi các giá trị cùng T

```java
static <T> void replaceFirst(List<T> list, T replacement) {
    list.set(0, replacement);
}
```

`List<T>` liên kết kiểu của list và replacement. Đây thường là thiết kế thích hợp nếu method cần ghi một T do caller cung cấp và vẫn đọc T từ list.

Dùng `List<? extends T>` sẽ khó ghi replacement. Dùng `List<? super T>` lại không bảo đảm đọc ra T.

### 12.2. Trả về wildcard làm caller khó sử dụng

Một API:

```java
static List<? extends Animal> makeAnimals() {
    return List.of(new Dog(), new Cat());
}
```

có thể hợp lệ nếu chỉ muốn công bố danh sách đọc được. Nhưng nếu API thật sự tạo ra `List<Animal>` rõ ràng, return type:

```java
static List<Animal> makeAnimals() {
    return new ArrayList<>(List.of(new Dog(), new Cat()));
}
```

dễ dùng hơn khi caller cần thêm Animal.

Không chọn wildcard ở return type chỉ để “nâng tính generic”; nó có thể đẩy phức tạp về phía caller.

### 12.3. Không dùng wildcard để che thiếu mô hình domain

Nếu một method cần biết liệu đầu vào là danh sách Dog hay Cat để thực hiện hành động rất khác nhau, `List<? extends Animal>` không tự cung cấp runtime generic argument. Hãy dùng polymorphism trên Animal, strategy, visitor hoặc cấu trúc domain rõ thay vì cast `List<?>` về List<Dog> một cách unchecked.

### 12.4. Không nhầm `? extends` với immutability

`List<? extends T>` chỉ cung cấp contract hạn chế ở compile time, không đóng băng object thật. Khi cần không cho người khác sửa collection, dùng copy/unmodifiable view theo contract, cùng kiểm soát aliasing.

## 13. Ví dụ Java 17 hoàn chỉnh: PECS trong API thực tế

Tạo file **`PecsApiDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;
import java.util.function.Function;

public class PecsApiDemo {
    static class Animal {
        private final String name;

        Animal(String name) {
            this.name = name;
        }

        String name() {
            return name;
        }

        @Override
        public String toString() {
            return getClass().getSimpleName()
                    + "(" + name + ")";
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

    static <T> void appendAll(
            List<? extends T> source,
            Collection<? super T> target) {
        for (T item : source) {
            target.add(item);
        }
    }

    static <T, R> void transformAll(
            Iterable<? extends T> source,
            Function<? super T, ? extends R> mapper,
            Collection<? super R> target) {
        for (T item : source) {
            target.add(mapper.apply(item));
        }
    }

    static <T> List<T> concat(
            List<? extends T> left,
            List<? extends T> right) {
        List<T> result = new ArrayList<>(
                left.size() + right.size());
        result.addAll(left);
        result.addAll(right);
        return result;
    }

    static void addDefaultDog(List<? super Dog> target) {
        target.add(new Dog("Bolt"));
    }

    static String firstName(
            List<? extends Animal> animals) {
        return animals.get(0).name();
    }

    static void swapFirstTwo(List<?> items) {
        swapCaptured(items);
    }

    private static <T> void swapCaptured(List<T> items) {
        T first = items.get(0);
        items.set(0, items.get(1));
        items.set(1, first);
    }

    public static void main(String[] args) {
        List<Dog> dogs = new ArrayList<>(
                List.of(new Dog("Rex"), new Dog("Amy")));
        List<Cat> cats = new ArrayList<>(
                List.of(new Cat("Miu")));

        List<Animal> animals = new ArrayList<>();
        List<Object> objects = new ArrayList<>();

        appendAll(dogs, animals);
        appendAll(dogs, objects);
        addDefaultDog(animals);

        System.out.println("animals=" + animals);
        System.out.println("objects=" + objects);
        System.out.println("first=" + firstName(dogs));

        List<Animal> combined = concat(dogs, cats);
        System.out.println("combined=" + combined);

        List<String> names = new ArrayList<>();
        Function<Animal, String> getName = Animal::name;
        transformAll(dogs, getName, names);
        System.out.println("names=" + names);

        Comparator<Animal> byName =
                Comparator.comparing(Animal::name);
        dogs.sort(byName);
        System.out.println("sorted=" + dogs);

        List<Integer> numbers = new ArrayList<>(
                List.of(3, 7));
        List<Number> numericTargets = new ArrayList<>(
                List.of(0, 0, 0));

        Collections.copy(numericTargets, numbers);
        System.out.println("copy=" + numericTargets);

        List<String> words = new ArrayList<>(
                List.of("one", "two"));
        swapFirstTwo(words);
        System.out.println("swapped=" + words);

        List<?> unknown = dogs;
        System.out.println("unknown-read=" + unknown.get(0));

        List<? super Dog> sink = animals;
        Object readBack = sink.get(0);
        System.out.println("super-read=" + readBack);
    }
}
```

Biên dịch với Java 17:

```bash
javac --release 17 -Xlint:all PecsApiDemo.java
java PecsApiDemo
```

Đã kiểm chứng: chương trình biên dịch thành công **không có warning** với `-Xlint:all` và cho stdout chính xác:

```text
animals=[Dog(Rex), Dog(Amy), Dog(Bolt)]
objects=[Dog(Rex), Dog(Amy)]
first=Rex
combined=[Dog(Rex), Dog(Amy), Cat(Miu)]
names=[Rex, Amy]
sorted=[Dog(Amy), Dog(Rex)]
copy=[3, 7, 0]
swapped=[two, one]
unknown-read=Dog(Amy)
super-read=Dog(Rex)
```

### 13.1. `animals` và `objects`

`appendAll(dogs, animals)` và `appendAll(dogs, objects)` đều hợp lệ nhờ liên kết `<T>` giữa producer và consumer. Sau đó `addDefaultDog(animals)` thêm `Dog(Bolt)`.

`List<Dog>` không cần bị ép hoặc copy thành `List<Animal>` **trước khi truyền**. Các giá trị được copy vào danh sách đích trong method vì đó là yêu cầu cụ thể của `appendAll`.

### 13.2. `first=Rex`

`firstName(List<? extends Animal>)` nhận `List<Dog>` và đọc một `Animal`, gọi `name()`. API không cần biết type argument chính xác của list.

### 13.3. `combined`

`concat` tạo một danh sách kết quả có thể chứa cả Dog và Cat. Caller khai báo `List<Animal>`, compiler suy luận T phù hợp. Không có sự gán sai `List<Dog>` sang `List<Animal>`; đây là **một collection mới**.

### 13.4. `names`

`Function<Animal,String>` có thể xử lý Dog vì đầu vào mapper là `? super T`. `transformAll` đọc Dog từ `Iterable<? extends T>` và ghi String vào `Collection<? super R>`.

### 13.5. `sorted`

`Comparator<Animal>` được chấp nhận bởi `List<Dog>.sort(Comparator<? super Dog>)`. Nó so sánh Dog thông qua hành vi đã định nghĩa trên Animal. Kết quả sắp xếp Amy trước Rex.

### 13.6. `copy=[3, 7, 0]`

`Collections.copy` **ghi đè** hai vị trí đầu của danh sách đích có ba phần tử. Không phải append: vị trí thứ ba giữ `0`.

### 13.7. `swapped=[two, one]`

Helper generic capture type của một `List<?>` cụ thể rồi đọc/ghi chính những phần tử cũ. Đây không phải thao tác thêm một String bất kỳ vào một List<?>.

### 13.8. `unknown-read` và `super-read`

`List<?> unknown` cho phép đọc như Object. `List<? super Dog> sink` cũng chỉ cho đọc như Object. Runtime object tình cờ là Dog trong ví dụ, nhưng compiler không thể suy ra `Dog` chỉ từ chữ ký `? super Dog`.

## 14. Bốn ví dụ cố ý không biên dịch

Hãy đặt **mỗi ví dụ trong tệp riêng** để quan sát đúng diagnostic, không chép các lỗi này vào `PecsApiDemo.java`.

### 14.1. `WrongInvariant.java`

```java
import java.util.List;

class WrongInvariant {
    static class Animal {
    }

    static class Dog extends Animal {
    }

    static void test(List<Dog> dogs) {
        List<Animal> animals = dogs;
    }
}
```

Chạy:

```bash
javac --release 17 WrongInvariant.java
```

Compiler báo:

```text
error: incompatible types:
List<Dog> cannot be converted to List<Animal>
```

Giải pháp nếu chỉ đọc:

```java
List<? extends Animal> animals = dogs;
```

Nếu cần một `List<Animal>` độc lập để thêm Cat:

```java
List<Animal> animals = new ArrayList<>(dogs);
```

Đoạn sửa cần import `ArrayList` nếu ở tệp riêng.

### 14.2. `WrongProducer.java`

```java
import java.util.List;

class WrongProducer {
    static class Animal {
    }

    static class Dog extends Animal {
    }

    static void test(List<? extends Animal> source) {
        source.add(new Dog());
    }
}
```

Chạy:

```bash
javac --release 17 WrongProducer.java
```

Compiler báo nội dung chính:

```text
error: incompatible types:
Dog cannot be converted to CAP#1
```

`CAP#1` là capture type chưa biết, có upper bound Animal. Nếu danh sách thật là `List<Cat>`, thêm Dog sẽ sai.

**Sửa:** nếu thực sự là đích nhận Dog, định nghĩa API nhận `List<? super Dog>`. Nếu đây là nguồn, đừng thêm phần tử vào nó.

### 14.3. `WrongConsumer.java`

```java
import java.util.List;

class WrongConsumer {
    static class Animal {
    }

    static class Dog extends Animal {
    }

    static void test(List<? super Dog> target) {
        Dog dog = target.get(0);
    }
}
```

Chạy:

```bash
javac --release 17 WrongConsumer.java
```

Compiler báo:

```text
error: incompatible types:
CAP#1 cannot be converted to Dog
```

Một `List<? super Dog>` có thể là `List<Object>`; phần tử hiện có không chắc là Dog. Dùng `Object dog = target.get(0)` nếu chỉ cần một Object, hoặc thiết kế chữ ký khác khi cần đọc đúng Dog.

### 14.4. `WrongWildcard.java`

```java
import java.util.List;

class WrongWildcard {
    static void test(List<?> input) {
        input.add("hello");
    }
}
```

Chạy:

```bash
javac --release 17 WrongWildcard.java
```

Compiler báo:

```text
error: incompatible types:
String cannot be converted to CAP#1
```

`List<?>` có type argument chưa biết. Nếu method cần ghi String, dùng `List<? super String>` hoặc `List<String>` theo khả năng đọc/ghi cần thiết.

Các trường hợp sai trên đã được kiểm tra trực tiếp bằng `javac --release 17`. Số dòng và tên capture variable có thể khác theo code/JDK, nhưng nguyên nhân type safety không thay đổi.

## 15. Thiết kế PECS cho API có nhiều thao tác

Một API thực thường có nhiều chức năng đọc/ghi khác nhau. Đừng cố ép tất cả vào **một** chữ ký wildcard quá tổng quát.

### 15.1. API chỉ đọc

```java
static double sum(
        Collection<? extends Number> numbers) {
    double result = 0;
    for (Number n : numbers) {
        result += n.doubleValue();
    }
    return result;
}
```

Ví dụ method minh họa cần import `Collection`. Nó đọc Number, không sửa tập dữ liệu. `? extends Number` cho caller đưa collection chứa Integer, Double và subtype Number khác.

### 15.2. API chỉ ghi

```java
static void emitDefaults(
        Collection<? super Integer> target) {
    target.add(1);
    target.add(2);
}
```

Nó có thể nhận `Collection<Integer>`, `Collection<Number>`, `Collection<Object>` khi những collection ấy có thể sửa.

### 15.3. API copy giữa nguồn và đích

```java
static <T> void transfer(
        Iterable<? extends T> source,
        Collection<? super T> target) {
    for (T value : source) {
        target.add(value);
    }
}
```

T liên kết loại phần tử đi qua cả hai phía. `Iterable` có thể phù hợp hơn `List` nếu chỉ cần vòng lặp.

### 15.4. API đọc và sửa theo cùng một kiểu

```java
static <T> void replaceFirst(
        List<T> values, T replacement) {
    values.set(0, replacement);
}
```

Không ép thành wildcard nếu T phải đồng nhất ở nơi đọc/ghi và giữa các tham số.

### 15.5. API chỉ cần kích thước

```java
static int sizeOf(Collection<?> values) {
    return values.size();
}
```

`<?>` diễn đạt chính xác vì không có quan hệ kiểu nào cần được đặt tên.

## 16. Wildcard ở return type và public APIs

Một nguyên tắc thiết kế hữu ích là **thường ưu tiên wildcard cho input parameters**, ít khi trả về wildcard nếu caller cần thao tác tiếp.

Ví dụ:

```java
static List<? extends Animal> getAnimals() {
    return List.of(new Dog(), new Cat());
}
```

Caller có thể duyệt Animal nhưng không dễ thêm Animal qua kiểu return đó.

Nếu method làm chủ collection và thực sự công bố danh sách Animal:

```java
static List<Animal> getAnimals() {
    List<Animal> result = new ArrayList<>();
    result.add(new Dog());
    result.add(new Cat());
    return result;
}
```

thì kiểu return `List<Animal>` có thể rõ ràng hơn.

Tuy vậy return wildcard **không luôn sai**. Trong những API cần biểu đạt một tập cụ thể chưa xác định hoặc bảo vệ contract đọc mà không cho caller ghi kiểu tùy ý, nó có thể phù hợp. Quyết định dựa trên nhu cầu caller, không theo một lệnh cấm cứng.

### 16.1. `? extends` không thực hiện defensive copy

Nếu trả thẳng một mutable list dưới kiểu `List<? extends Animal>`, caller vẫn có thể có alias khác sửa list. Hoặc chính caller có thể gọi `clear()` trên tham chiếu nếu object cho phép.

Nếu mục tiêu là tránh mutation hoặc giữ snapshot, dùng các biện pháp về ownership và unmodifiable copies thích hợp, không chỉ wildcard.

### 16.2. API với nhiều phiên bản generic

Khi API có một helper generic và một overload nhận `List<?>`, cần cân nhắc **erasure/name clash**. Hai overload chỉ khác type argument của cùng raw List có thể không được định nghĩa chung vì erasure trùng nhau.

Ví dụ cố tình sai:

```java
// Không thể cùng nằm trong một class:
// void inspect(List<String> values) {}
// void inspect(List<Integer> values) {}
```

Cả hai erase thành tham số `List`. Wildcard giúp linh hoạt, nhưng không cho phép overload methods chỉ khác generic type arguments đã bị xóa.

## 17. PECS và `Optional`, `Stream`, `Predicate`

Quy tắc hướng input/output còn xuất hiện trong các API không phải Collection.

### 17.1. `Optional.map`

Chữ ký có dạng:

```java
<U> Optional<U> map(
    Function<? super T, ? extends U> mapper)
```

Mapper **nhận T** (consumer) nên input có `? super T`; mapper **sinh U** (producer) nên output có `? extends U`.

Đây là chính mẫu Function của `transformAll`, chỉ khác container Optional.

### 17.2. `Stream.map`

Stream API cũng dùng `Function<? super T, ? extends R>` để cho phép lambda/method reference tiêu thụ supertype và sinh subtype của result type theo inference.

Ví dụ:

```java
List<String> names = dogs.stream()
        .map(Animal::name)
        .toList();
```

Phương thức trên giả định `dogs` là `List<Dog>` và có method name ở Animal. `Animal::name` nhận một Animal nên có thể áp dụng cho từng Dog.

### 17.3. `Predicate<? super T>`

Một predicate **tiêu thụ** T để kiểm tra:

```java
static <T> long countMatching(
        Iterable<? extends T> source,
        Predicate<? super T> check) {
    long count = 0;
    for (T value : source) {
        if (check.test(value)) count++;
    }
    return count;
}
```

Ví dụ này cần import `java.util.function.Predicate`. Nguồn là producer (`extends`), predicate là consumer (`super`).

### 17.4. Không đổi hướng wildcard theo tên interface

`Supplier<? extends T>` là producer vì phương thức `get()` **trả** T. `Consumer<? super T>` là consumer vì phương thức `accept` **nhận** T. `Comparator<? super T>` tiêu thụ đối tượng so sánh.

Hãy nhìn **cách interface dùng T**, không chỉ tên interface. Một `Function` vừa tiêu thụ input vừa tạo output nên có cả hai hướng.

## 18. Wildcard bounds và suy luận kiểu

Một phương thức PECS tổng quát:

```java
static <T> void appendAll(
        List<? extends T> from,
        Collection<? super T> to) {
    to.addAll(from);
}
```

khi gọi:

```java
appendAll(dogs, animals);
```

cần tìm một T cho phép:

- Elements của `dogs` đọc được dưới dạng T.
- `animals` nhận được T.

Compiler giải những ràng buộc này qua generic method inference.

### 18.1. Explicit type witness nếu cần

Trong một số trường hợp, bạn có thể viết:

```java
MyClass.<Animal>appendAll(dogs, animals);
```

`MyClass` là class chứa static method trong ví dụ minh họa. Chỉ rõ T=Animal có thể giúp giải thích ý định trong code khó suy luận, nhưng **không biến một phép gán sai thành đúng**.

Khi không cần, để Java inference thường giúp code gọn hơn.

### 18.2. Khi inference báo incompatible bounds

Nếu method nhận producer/consumer với kiểu không tương thích, compiler có thể báo:

```text
inference variable T has incompatible bounds
```

Lúc đó hãy ghi ra các quan hệ subtype cần thỏa và xác định ràng buộc nào xung đột. Ví dụ cố chuyển một `List<Cat>` vào một `List<Dog>` là không an toàn vì Cat không thuộc kiểu phần tử Dog.

Không thêm raw cast hoặc `@SuppressWarnings("unchecked")` chỉ để tắt compiler. Nếu cần chuyển đổi Cat thành Dog vì nghiệp vụ, hãy định nghĩa một **mapper** thật sự có return type Dog, thay vì ép Generics bỏ qua loại dữ liệu.

## 19. Không phải wildcard nào cũng có thể kết hợp tùy ý

### 19.1. Hai wildcard không tự có quan hệ với nhau

```java
static void broken(
        List<?> from, List<?> to) {
    // Không biên dịch:
    // to.add(from.get(0));
}
```

Mỗi dấu `?` có **capture type riêng**. Compiler không được giả định type argument ẩn của hai list giống nhau.

Giải pháp khi muốn copy an toàn là một `<T>` liên kết các phía:

```java
static <T> void copyOne(
        List<? extends T> from,
        List<? super T> to) {
    to.add(from.get(0));
}
```

### 19.2. `? extends Number` không phải `? super Number`

- `List<? extends Number>` có thể chứa Integer, Double, BigDecimal; đọc như Number.
- `List<? super Number>` có thể là List<Number> hoặc List<Object>; có thể thêm Number.

Đảo wildcard làm thay đổi hẳn chức năng của API. Một phương thức chỉ muốn tính tổng không cần `? super Number`. Một phương thức ghi Number vào đích không nên nhận `? extends Number`.

### 19.3. `List<Object>` không phải “nhận mọi list”

```java
static void inspect(List<Object> list) {
}
```

chỉ nhận những tham chiếu phù hợp `List<Object>`, không tự nhận `List<String>`. Nếu method chỉ quan sát mọi list, dùng `List<?>`; nếu cần đọc như một parent type, dùng `List<? extends Parent>`.

## 20. Những ngộ nhận thường gặp

**Ngộ nhận 1: `Dog extends Animal` kéo theo `List<Dog> extends List<Animal>`.** Sai: Generic parameterized types invariant.

**Ngộ nhận 2: `? extends T` là cách viết List chỉ đọc tuyệt đối.** Sai: nó hạn chế ghi phần tử T tùy ý; không bảo đảm object immutable hoặc không có alias sửa.

**Ngộ nhận 3: `? super Dog` đọc ra Dog được.** Sai: phần tử có thể tới từ `List<Object>`; đọc dưới kiểu an toàn chung `Object`.

**Ngộ nhận 4: `List<?>` chính là `List<Object>`.** Sai: `List<?>` nhận các danh sách với type arguments khác nhau; `List<Object>` không phải supertype của mọi `List<T>`.

**Ngộ nhận 5: Chỉ dùng PECS mà không cần `<T>`.** Sai: khi liên kết nguồn, đích, mapper và return type, type parameter `<T>` giúp các phần của chữ ký có chung quan hệ kiểu.

**Ngộ nhận 6: Mọi API nên dùng `? extends` ở đầu vào.** Sai: nếu đầu vào là đích để thêm T, phải cân nhắc `? super T`.

**Ngộ nhận 7: `? super T` có nghĩa cho phép thêm mọi supertype của T.** Sai: method có thể thêm T hoặc subtype; không được tùy ý thêm Object/Animal khi đích thực có thể là List<Dog>.

**Ngộ nhận 8: PECS làm copy dữ liệu hoặc bảo đảm không mutation.** Sai: wildcard chỉ giới hạn compile-time typing. Side effects, aliasing, null và mutability cần contract riêng.

**Ngộ nhận 9: `Collections.copy` có nghĩa append.** Sai: nó ghi đè các phần tử ở index, đích phải có đủ kích thước.

**Ngộ nhận 10: `Comparator<Animal>` không dùng được với `List<Dog>`.** Sai: `List.sort` nhận `Comparator<? super E>` nên Comparator của Animal có thể so sánh Dog.

**Ngộ nhận 11: Wildcard capture là mẹo bỏ qua type safety.** Sai: helper đặt tên cho một captured type để bảo toàn quan hệ, không làm mọi object khác kiểu có thể được thêm vào list.

**Ngộ nhận 12: Chỉ cần compiler chấp nhận `add` là collection chắc chắn cho sửa.** Sai: runtime collection có thể unmodifiable hoặc từ chối null.

## 21. Checklist chọn wildcard theo vai trò của tham số

Khi thiết kế một method public, hãy hỏi lần lượt:

1. **Method chỉ cần đọc các phần tử như T?** Dùng `Collection<? extends T>` hoặc interface phù hợp.
2. **Method chỉ cần đưa các phần tử T vào đích?** Dùng `Collection<? super T>`.
3. **Method chỉ cần size/duyệt Object?** Dùng `Collection<?>` thay vì khai báo T không cần thiết.
4. **Method cần liên kết kiểu giữa nhiều tham số?** Khai báo `<T>` và đặt wildcard đúng hướng cho từng tham số.
5. **Method cần vừa đọc và ghi trên cùng cấu trúc theo T?** Xem `Collection<T>`/`List<T>` hoặc capture helper.
6. **Có cần list semantics thật không?** Nếu không, cân nhắc `Iterable`/`Collection`.
7. **Return type có thể giữ một `List<T>` rõ ràng không?** Tránh wildcard trả về gây khó khăn cho caller khi không cần.
8. **Dữ liệu có null hoặc collection unmodifiable không?** Viết contract và kiểm thử độc lập với Generics.
9. **Nguồn và đích có thể alias cùng object không?** Đánh giá side effect và modification during iteration.
10. **Cần conversion thực sự giữa hai loại không có subtype relation?** Dùng mapper/adapter, không ép cast unchecked.
11. **Có compiler warning về raw/unchecked types không?** Sửa nguồn type safety, không tự động suppress.
12. **Có test cho các trường hợp subtype, supertype và lỗi compile không?** Đảm bảo API thật sự nhận được các input mong muốn mà vẫn từ chối sai kiểu.

### 21.1. Quy trình review nhanh

Một reviewer có thể đọc chữ ký:

```java
static <T, R> void transformAll(
        Iterable<? extends T> source,
        Function<? super T, ? extends R> mapper,
        Collection<? super R> target)
```

và hỏi:

- `source` có đúng producer của T không?
- `mapper` có nhận T/supertype và trả R/subtype không?
- `target` có nhận R không?
- Có method nào sửa source hoặc lộ mutable alias trái hợp đồng không?
- Return/exception semantics có rõ không?

Nếu câu trả lời nhất quán, chữ ký PECS đang phản ánh đúng luồng dữ liệu.

## 22. Bài tập có đáp án

### Bài 1. Nhận `List<Dog>` để đọc Animal

Viết kiểu tham số của method đọc tên các Animal mà caller có thể truyền `List<Dog>` hoặc `List<Cat>`.

**Đáp án:**

```java
static void printAll(List<? extends Animal> source) {
    for (Animal value : source) {
        System.out.println(value.name());
    }
}
```

Vì source là producer của Animal, dùng `? extends Animal`.

### Bài 2. Thêm Dog vào nhiều kiểu list

Muốn nhận `List<Dog>`, `List<Animal>` và `List<Object>` để thêm Dog, dùng kiểu nào?

**Đáp án:**

```java
static void addDog(List<? super Dog> target) {
    target.add(new Dog());
}
```

Đích là consumer của Dog.

### Bài 3. Vì sao đọc một Dog từ `List<? super Dog>` không an toàn?

**Đáp án:** Tham chiếu có thể thật là `List<Object>` đã chứa dữ liệu không phải Dog. Kiểu đọc an toàn mà compiler bảo đảm là Object, không phải Dog.

### Bài 4. Sửa method copy cứng nhắc

```java
static <T> void copy(List<T> src, List<T> dest) {
    dest.addAll(src);
}
```

Làm sao cho phép copy Dog sang List<Animal>?

**Đáp án:**

```java
static <T> void copy(
        List<? extends T> src,
        List<? super T> dest) {
    dest.addAll(src);
}
```

Source producer (`extends`), destination consumer (`super`).

### Bài 5. `List<?>` và `List<Object>` có giống nhau không?

**Đáp án:** Không. `List<?>` có thể tham chiếu tới `List<String>`, `List<Integer>` và nhiều kiểu khác; `List<Object>` không phải supertype của tất cả `List<T>`.

### Bài 6. `Collections.copy` có thêm mới các phần tử vào danh sách đích không?

**Đáp án:** Không. Nó thay các phần tử theo index và yêu cầu đích có kích thước đủ. Nếu muốn append, dùng `addAll` hoặc API chuyên thêm phần tử.

### Bài 7. Vì sao có `Comparator<? super E>` trong `List.sort`?

**Đáp án:** Comparator nhận các phần tử E để so sánh, tức là **consumer** của E. Comparator của supertype như Animal có thể so sánh các Dog, nên `? super E` phù hợp.

### Bài 8. Vì sao một `Function` vừa có `super` vừa có `extends`?

**Đáp án:** Function vừa **tiêu thụ input** T vừa **sản xuất output** R, nên input `? super T` và output `? extends R`.

### Bài 9. Hai `List<?>` có thể copy qua nhau trực tiếp không?

**Đáp án:** Không phải bằng cách tùy ý `to.add(from.get(0))`, vì hai wildcard có capture types độc lập. Cần một type parameter liên kết nguồn/đích qua `? extends T` và `? super T`, hoặc một helper capture khi thao tác trên cùng nguồn phù hợp.

### Bài 10. Khi nào dùng `List<T>` thay vì `List<? extends T>`?

**Đáp án:** Khi method cần quan hệ kiểu chính xác để **đọc lẫn ghi T trên cùng list**, hoặc cần caller cung cấp một T và lưu vào list đó. `List<? extends T>` không cho thêm T tùy ý vì type argument thật có thể hẹp hơn T.

### Bài 11. `List<? extends Animal>` có chắc immutable không?

**Đáp án:** Không. Nó có thể là mutable `ArrayList<Dog>`; wildcard chỉ giới hạn thao tác theo generic type, không chặn mọi mutation hoặc alias.

### Bài 12. Compiler từ chối đưa Cat vào `List<? super Dog>` vì sao?

**Đáp án:** Đích có thể là `List<Dog>`, nên Cat không tương thích. `? super Dog` bảo đảm an toàn khi thêm Dog/subtype của Dog, không phải mọi Animal.

## 23. Tổng kết

**PECS là công cụ thiết kế đầu vào linh hoạt có kiểm tra kiểu**, không phải mẹo ghi `? extends`/`? super` tùy ý:

- **Producer Extends**: `Collection<? extends T>` cho phép caller cung cấp collections có phần tử T hoặc subtype; đọc được như T.
- **Consumer Super**: `Collection<? super T>` cho phép caller cung cấp collections có thể nhận T; thêm T an toàn.
- **Kết hợp `<T>`** để liên kết source/target: `copy(List<? extends T>, List<? super T>)`.
- **`Function<? super T, ? extends R>`** vừa tiêu thụ T, vừa sinh R; `Comparator<? super T>` tiêu thụ T để so sánh.
- **`<?>`** thích hợp khi không cần nói đến kiểu phần tử cụ thể; wildcard capture helper thích hợp khi cần giữ nhất quán một kiểu chưa biết.
- **`List<T>`** vẫn là lựa chọn đúng khi method phải vừa đọc vừa ghi chính T.

Dù compiler xác minh PECS, contract ứng dụng vẫn phải quy định kích thước, null, mutability, ownership và aliasing. Một API tốt chọn **kiểu tham số rộng đủ để nhận đầu vào hợp lệ nhưng không rộng đến mức mất bảo đảm**, đồng thời trả kiểu kết quả dễ sử dụng cho caller. Kết hợp quy tắc này với các ví dụ Java 17 và kiểm thử compiler sẽ giúp bạn đọc và thiết kế các Generic APIs rõ ràng, linh hoạt và an toàn.