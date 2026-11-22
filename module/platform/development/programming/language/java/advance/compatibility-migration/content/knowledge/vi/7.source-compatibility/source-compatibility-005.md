# Generics, suy luận kiểu và các trường hợp chỉ lỗi khi biên dịch lại

Trong một dự án Java lâu năm, artifact đã biên dịch có thể vẫn chạy trên môi trường hiện tại, nhưng source code lại không biên dịch được khi nâng compiler hoặc cập nhật thư viện. Một nhóm nguyên nhân thường gặp nằm ở generic type, type inference và các thay đổi trong chữ ký API.

Generics được kiểm tra chủ yếu ở thời điểm biên dịch và được triển khai bằng type erasure. Vì vậy, hai phiên bản API có thể giữ cùng method descriptor ở mức JVM nhưng khác generic signature mà compiler sử dụng. Binary cũ đôi khi vẫn liên kết được, trong khi source cũ không còn hợp lệ khi biên dịch lại. Ngược lại, một thay đổi generic cũng có thể làm thay đổi erasure và gây lỗi liên kết thật sự.

Bài học này trình bày cách đọc chữ ký generic, hiểu suy luận kiểu, nhận diện các tình huống chỉ lộ ra khi compile lại và điều tra nguyên nhân theo bằng chứng. Đây là một phần của khảo sát tương thích mã nguồn trong Java Advance Compatibility Migration.

## 1. Ba lớp tương thích cần phân biệt

Khi một thư viện hoặc compiler thay đổi, hãy trả lời riêng ba câu hỏi:

1. **Source compatibility:** mã nguồn hiện tại có biên dịch được với compiler và API mới không?
2. **Binary compatibility:** bytecode đã tạo trước đó có liên kết được với class và method mới không?
3. **Behavioral compatibility:** chương trình sau khi liên kết có tiếp tục xử lý dữ liệu và cho kết quả đúng không?

Không thể suy ra câu trả lời của cả ba từ một lần build thành công hoặc một lần chạy thành công.

Ví dụ, thư viện cũ khai báo:

```java
package com.example;

import java.util.List;

public interface Registry {
    List findAll();
}
```

Client dùng:

```java
Registry registry = obtainRegistry();
List<Integer> ids = registry.findAll();
```

Vì method trả về raw `List`, compiler có thể chấp nhận phép gán và phát cảnh báo unchecked conversion. Phiên bản thư viện mới khai báo:

```java
public interface Registry {
    List<String> findAll();
}
```

Khi compile lại, `List<String>` không thể gán cho `List<Integer>`, nên source bị lỗi. Tuy nhiên, descriptor JVM của method ở cả hai phiên bản vẫn là:

```text
findAll:()Ljava/util/List;
```

Thông tin generic được lưu trong `Signature` attribute của class file, còn descriptor đã xóa được JVM dùng để liên kết method. Do descriptor không đổi, binary cũ có thể vẫn gọi được method mới. Nhưng nếu thư viện mới trả về `String` trong khi client cũ đọc phần tử và ép thành `Integer`, chương trình có thể gặp `ClassCastException`.

Ví dụ này cho thấy thay đổi generic có thể phá source compatibility mà không phá binary linkage, nhưng vẫn gây lỗi hành vi.

## 2. Generics và type erasure

### 2.1. Mục đích của generics

Generics cho phép biểu diễn kiểu dữ liệu và ràng buộc kiểu trong API:

```java
List<String> names = new ArrayList<>();
names.add("Mai");
String first = names.get(0);
```

Compiler kiểm tra kiểu phần tử ở thời điểm biên dịch. `List<String>` và `List<Integer>` không phải hai class runtime riêng; cả hai đều dựa trên `java.util.List`.

### 2.2. Cách type erasure hoạt động

Khi biên dịch, compiler xóa type parameter theo các quy tắc chính:

- Type parameter không có bound được thay bằng `Object`.
- Type parameter có bound được thay bằng kiểu bound đầu tiên.
- Kiểu tham số hóa như `List<String>` được xóa về raw type `List`.
- Compiler có thể chèn cast ở phía gọi và sinh bridge method để giữ quy tắc dispatch sau erasure.

Ví dụ:

```java
public static <T> T identity(T value) {
    return value;
}
```

Descriptor sau erasure của method nhận và trả về `Object`:

```text
identity:(Ljava/lang/Object;)Ljava/lang/Object;
```

Nếu method có bound:

```java
public static <T extends Number> T normalize(T value) {
    return value;
}
```

Kiểu xóa của `T` là `Number`, nên descriptor dùng `Number` thay cho `Object`.

### 2.3. Descriptor và generic signature

Trong class file, cần phân biệt:

| Thành phần | Vai trò |
| --- | --- |
| JVM descriptor | Biểu diễn kiểu tham số và kiểu trả về sau erasure; được dùng cho liên kết bytecode. |
| `Signature` attribute | Giữ thông tin type parameter, wildcard và kiểu generic để compiler, reflection và công cụ đọc metadata sử dụng. |

Ví dụ:

```java
public interface Cache {
    <T> T get(String key);
}
```

Descriptor đã xóa là:

```text
(Ljava/lang/String;)Ljava/lang/Object;
```

Nếu API đổi thành `Object get(String key)`, descriptor vẫn như trên, nhưng generic signature đã thay đổi. Client cũ có câu lệnh `String value = cache.get("name");` có thể không compile lại được vì compiler chỉ còn thấy kiểu trả về `Object`.

Khi so sánh hai phiên bản thư viện, chỉ so tên method và descriptor là chưa đủ. Cần xem cả `Signature` attribute và contract kiểu mà source client nhìn thấy.

### 2.4. Bridge method

Compiler có thể sinh bridge method để bảo toàn đa hình sau khi xóa generic type. Ví dụ:

```java
class Node<T> {
    public void set(T value) { }
}

class IntegerNode extends Node<Integer> {
    @Override
    public void set(Integer value) { }
}
```

Ở mức source, `IntegerNode.set(Integer)` ghi đè method generic đã được chuyên biệt hóa. Sau erasure, chữ ký của lớp cha dùng `Object`, trong khi method của lớp con dùng `Integer`. Compiler có thể tạo bridge method nhận `Object`, kiểm tra/ép kiểu rồi chuyển tiếp đến `set(Integer)`.

Khi điều tra lỗi linkage hoặc hành vi override, hãy nhớ rằng bytecode có thể chứa method tổng hợp (`synthetic`) mà source không thể hiện trực tiếp. `javap -v` giúp xem các cờ và method được compiler sinh.

## 3. Cách compiler suy luận kiểu

### 3.1. Suy luận type argument của generic method

Người gọi không phải lúc nào cũng viết type argument. Compiler tạo các ràng buộc từ kiểu đối số, kiểu đích và chữ ký method rồi tìm nghiệm phù hợp.

```java
static <T> T first(List<T> values) {
    return values.get(0);
}

String name = first(Arrays.asList("Lan", "Minh"));
```

Compiler suy ra `T` là `String`. Có thể viết tường minh để làm rõ ý định:

```java
String name = MyUtils.<String>first(Arrays.asList("Lan", "Minh"));
```

Nếu lời gọi không compile, thử chỉ định type argument tường minh có thể giúp xác định constraint nào không được thỏa mãn. Đây là kỹ thuật chẩn đoán; nếu API mới không còn generic method tương ứng thì cú pháp này không thể khôi phục contract cũ.

### 3.2. Target typing

Target type là kiểu mà một biểu thức cần đáp ứng trong ngữ cảnh sử dụng. Kiểu đích có thể tham gia vào quá trình suy luận:

```java
List<String> names = Collections.emptyList();
```

`Collections.emptyList()` là generic method. Kiểu đích `List<String>` giúp compiler chọn `String` làm type argument.

Target typing cũng xuất hiện với lambda và method reference:

```java
Function<String, Integer> length = value -> value.length();
```

Kiểu tham số `value` được suy ra từ functional interface đích. Nếu API thay đổi overload hoặc kiểu đích, biểu thức lambda có thể được phân giải khác hoặc trở nên ambiguous.

### 3.3. Diamond operator

Diamond operator cho phép suy ra type argument khi tạo object generic:

```java
Map<String, List<Integer>> index = new HashMap<>();
```

Compiler dùng target type để suy ra kiểu của `HashMap`. Nếu biểu thức được chuyển sang một ngữ cảnh khác, chẳng hạn truyền qua nhiều overload hoặc gán vào biến có kiểu rộng hơn, kết quả suy luận có thể thay đổi.

### 3.4. Wildcard và capture conversion

Wildcard mô tả kiểu phần tử linh hoạt:

```java
void printNumbers(List<? extends Number> values) {
    for (Number value : values) {
        System.out.println(value);
    }
}
```

`? extends Number` cho phép truyền danh sách các kiểu con của `Number`, nhưng không thể thêm một `Integer` tùy ý vì kiểu phần tử cụ thể chưa biết.

Với `? super Integer`, có thể thêm `Integer` vào danh sách, nhưng khi đọc chỉ có thể đảm bảo kiểu `Object` nếu không có thông tin khác.

Capture conversion tạo ra một kiểu đại diện cho wildcard chưa biết. Một helper generic thường giúp compiler giữ quan hệ giữa các lần đọc/ghi:

```java
static void swapFirstTwo(List<?> values) {
    swapCaptured(values);
}

private static <T> void swapCaptured(List<T> values) {
    T first = values.get(0);
    values.set(0, values.get(1));
    values.set(1, first);
}
```

Khi chữ ký generic của API thay đổi, quan hệ capture mà compiler suy ra có thể không còn giống trước.

## 4. Những thay đổi generic có thể làm source compile thất bại

### 4.1. Raw type được thay bằng kiểu tham số hóa

API cũ:

```java
List findAll();
```

API mới:

```java
List<String> findAll();
```

Client gán kết quả vào `List<Integer>` có thể từng compile với unchecked warning, nhưng sẽ lỗi khi compile lại với API mới. Descriptor vẫn là `()Ljava/util/List;`; generic signature mới mới là thông tin khiến compiler từ chối.

### 4.2. Generic method bị đổi thành kiểu trả về cụ thể

API cũ:

```java
<T> T read(String key);
```

API mới:

```java
Object read(String key);
```

Client có thể từng gọi `String title = store.read("title");` mà không cần cast. Sau thay đổi, source phải dùng API typed khác hoặc chuyển đổi kiểu rõ ràng. Erasure vẫn có thể cho cùng descriptor trả về `Object`, nhưng source contract đã yếu đi.

### 4.3. Thay đổi type bound

Bound giới hạn kiểu được phép và quyết định erasure. Ví dụ:

```java
// Trước
<T extends Number> T normalize(T value);

// Sau
<T extends Integer> T normalize(T value);
```

Source truyền `Double` hoặc `Long` không còn hợp lệ. Vì bound đầu tiên thay đổi từ `Number` sang `Integer`, descriptor cũng thay đổi, nên binary cũ có thể gặp lỗi linkage.

Với intersection bound, kiểu bound đầu tiên quyết định erasure. Thay đổi bound đầu tiên có thể làm descriptor thay đổi dù các bound khác vẫn giữ nguyên.

### 4.4. Thêm overload làm thay đổi overload resolution

Compiler chọn overload dựa trên kiểu đối số, generic inference, target type và các quy tắc phân giải method. Khi thư viện thêm overload, lời gọi cũ có thể chọn method khác hoặc trở nên ambiguous.

Ví dụ:

```java
void register(Consumer<String> handler);
void register(Function<String, String> handler);

register(text -> text.trim());
```

Lambda expression có thể phù hợp với cả functional interface trả về `void` (nếu phần thân là statement expression) và functional interface trả về giá trị. Compiler có thể không chọn được overload duy nhất. Có thể làm rõ target type:

```java
Function<String, String> normalizer = text -> text.trim();
register(normalizer);
```

Khi lỗi xuất hiện sau khi nâng thư viện, xem toàn bộ overload candidates trong thông báo compiler và đối chiếu release notes của API.

### 4.5. Raw type và unchecked warning bị nâng thành lỗi

```java
List values = new ArrayList();
values.add("text");
List<String> names = values; // unchecked conversion
```

Source có thể compile nhưng tạo cảnh báo. Nếu build bật `-Werror` hoặc chính sách warning-as-error, pipeline có thể thất bại. Cần phân biệt lỗi kiểu thực sự với lỗi do chính sách build. Ưu tiên sửa raw type và giới hạn unchecked cast ở adapter nhỏ; không suppress cảnh báo trên diện rộng.

### 4.6. Generic varargs và heap pollution

```java
static <T> List<T> merge(List<T>... inputs) {
    List<T> result = new ArrayList<>();
    for (List<T> input : inputs) {
        result.addAll(input);
    }
    return result;
}
```

Generic varargs có thể phát cảnh báo heap pollution vì mảng runtime không giữ đầy đủ type argument. Chỉ dùng `@SafeVarargs` khi method thực sự an toàn và đáp ứng điều kiện của ngôn ngữ. Annotation này là cam kết của lập trình viên, không phải phép kiểm tra tự động.

## 5. Những nguyên nhân ngoài generics làm compile lại thất bại

Lỗi compile sau migration không phải lúc nào cũng do thay đổi của javac. Cần kiểm tra các yếu tố đi kèm:

- **Phiên bản dependency thay đổi:** compile classpath hiện tại có thể chứa API generic khác với phiên bản đã dùng khi tạo binary cũ.
- **Compiler plugin thay đổi:** Maven Compiler Plugin, Gradle compiler task hoặc annotation processor có thể thay đổi cấu hình và cách tạo mã.
- **Source/release khác nhau:** JDK 11 chạy compiler mới; nếu không khóa `--release` hoặc source level, dự án có thể vô tình dùng ngôn ngữ/API mới.
- **Generated source:** mã do JAXB, ORM metamodel generator, Lombok hoặc processor khác sinh ra có thể thay đổi theo phiên bản công cụ.
- **Cờ cảnh báo thay đổi:** `-Xlint`, `-Werror` hoặc cấu hình CI có thể biến cảnh báo cũ thành lỗi build.
- **Build không tái lập:** dependency snapshot, repository hoặc plugin version không được khóa có thể khiến hai lần compile dùng đầu vào khác nhau.

Do đó, khi so sánh JDK 8 và JDK 11, phải giữ ổn định dependency và cấu hình build trước khi kết luận lỗi là do compiler.

## 6. Phân biệt thay đổi compiler với thay đổi API

### 6.1. Ghi nhận cấu hình build hiệu lực

Thu thập các giá trị sau:

| Thông tin | Cần ghi nhận |
| --- | --- |
| Compiler JDK | Vendor, phiên bản và đường dẫn JDK thực tế. |
| Source level | Phiên bản cú pháp Java mà compiler chấp nhận. |
| Target bytecode | Phiên bản class file được tạo. |
| Release API | API nền tảng mà source được phép sử dụng. |
| Compile classpath | Phiên bản dependency mà compiler nhìn thấy. |
| Annotation processor | Phiên bản và cấu hình processor tạo source/class. |
| Compiler flags | `-Xlint`, `-Werror`, encoding và các tùy chọn khác. |

Với JDK 11, `--release 8` giúp biên dịch theo API và bytecode Java 8 trong phạm vi mà JDK 11 hỗ trợ. Điều này hữu ích trong giai đoạn chuyển tiếp, nhưng không biến compiler JDK 11 thành compiler JDK 8 và không thay thế việc kiểm tra dependency.

### 6.2. Kiểm tra dependency tree

Maven:

```bash
mvn dependency:tree -Dscope=compile
```

Gradle:

```bash
./gradlew dependencies --configuration compileClasspath
```

So sánh dependency compile giữa baseline và build mới. Nếu thư viện đổi generic signature, hãy xác định phiên bản chính xác trước khi điều chỉnh source.

### 6.3. Xem descriptor và generic signature bằng `javap`

```bash
javap -classpath path/to/library.jar -p -s -v com.example.Registry
```

So sánh:

- Descriptor sau erasure.
- `Signature` attribute.
- Các method overload mới hoặc bị loại bỏ.
- Bridge method và cờ `ACC_SYNTHETIC` nếu có.

Nếu descriptor đổi, điều tra binary linkage. Nếu descriptor giữ nguyên nhưng signature đổi, source compile lại vẫn có thể lỗi. Trong cả hai trường hợp, cần kiểm tra dữ liệu và hành vi runtime.

## 7. Cách xử lý lỗi theo nguyên nhân

### 7.1. Nếu API generic của thư viện thay đổi

Đọc migration guide và chọn một trong các hướng:

- Sửa source theo contract mới.
- Chuyển đổi dữ liệu tại adapter boundary.
- Dùng phiên bản dependency khác nếu sản phẩm phải duy trì source compatibility.
- Cập nhật đồng bộ các module/client được biên dịch độc lập.

Không ép kiểu để làm compiler im lặng nếu chưa xác minh dữ liệu thực tế. Cast chỉ chuyển lỗi từ compile time sang runtime.

### 7.2. Nếu inference không xác định được kiểu

Thử:

- Viết type argument tường minh cho generic method.
- Tạo biến trung gian có kiểu cụ thể.
- Khai báo kiểu functional interface cho lambda/method reference.
- Tách biểu thức phức tạp thành các bước nhỏ.
- Chọn overload rõ ràng theo tài liệu API.

Ví dụ:

```java
Function<String, Integer> parser = text -> Integer.valueOf(text);
result = converter.convert(parser);
```

Biến `parser` giúp cố định target type trước khi gọi API overloaded.

### 7.3. Nếu raw type hoặc unchecked warning là nguyên nhân

Thay raw type bằng kiểu tham số hóa phù hợp với dữ liệu. Nếu dữ liệu đến từ API legacy, kiểm tra và chuyển đổi ở một vị trí tập trung. Chỉ dùng `@SuppressWarnings` trên statement hoặc method nhỏ khi có kiểm soát rõ ràng.

### 7.4. Nếu lỗi đến từ generated source

Xác định processor/plugin tạo mã, phiên bản JDK mà processor hỗ trợ và phiên bản dependency mà generated source tham chiếu. Xóa output sinh cũ trong build directory thông qua clean build, sau đó sinh lại bằng cấu hình đã khóa. Không chỉnh tay generated source nếu nó sẽ bị ghi đè ở lần build tiếp theo; sửa schema, annotation, template hoặc plugin nguồn.

## 8. Kiểm thử và quản lý tương thích sau compile

Sau khi source compile thành công, cần kiểm tra:

- Unit test cho các generic API và kiểu dữ liệu thực tế.
- Integration test với implementation và dependency được dùng trong production.
- Các nhánh overload, lambda và method reference có ý nghĩa nghiệp vụ.
- Serialization/deserialization nếu generic type tham gia schema dữ liệu.
- Tương thích giữa client binary cũ và thư viện mới nếu có plugin hoặc client phát hành độc lập.
- Runtime trên JDK thấp nhất còn hỗ trợ và JDK đích migration.

Với thư viện public API, nên duy trì kiểm tra source compatibility và binary compatibility riêng. Có thể dùng công cụ so sánh API để phát hiện thay đổi chữ ký, nhưng vẫn phải đọc generic signature và kiểm tra hành vi.

## 9. Mẫu ghi nhận một lỗi generics trong migration

| Trường | Nội dung cần ghi |
| --- | --- |
| Module/source | Module, file và dòng phát sinh lỗi. |
| Compiler | JDK vendor/version, source/release và compiler flags. |
| API liên quan | Class, method, generic signature trước/sau. |
| Dependency | Artifact, version và compile classpath. |
| Thông báo lỗi | Toàn bộ diagnostic, overload candidates và warning. |
| Phân loại | Source incompatibility, warning-as-error, binary linkage hay runtime behavior. |
| Cách xử lý | Sửa source, đổi dependency, cập nhật processor hoặc điều chỉnh build policy. |
| Bằng chứng | Build log, `javap` output, test result và commit liên quan. |

Ghi lại cả những thay đổi đã thử nhưng không giải quyết được lỗi nếu chúng giúp xác định nguyên nhân. Không gộp nhiều lỗi generic khác nhau thành một ticket chung nếu mỗi lỗi thuộc một API hoặc dependency riêng.

## 10. Checklist hoàn thành khảo sát

- [ ] Đã xác định compiler JDK, source/release, target bytecode và cờ cảnh báo.
- [ ] Đã so sánh compile classpath giữa baseline và build migration.
- [ ] Đã tìm raw type, unchecked conversion/cast và generic varargs.
- [ ] Đã kiểm tra thay đổi generic return type, parameter, bound và overload.
- [ ] Đã so sánh descriptor và `Signature` attribute của API có thay đổi.
- [ ] Đã xem target typing, wildcard capture, lambda và method reference ở vị trí compile lỗi.
- [ ] Đã xác định annotation processor và generated source có liên quan.
- [ ] Đã phân biệt lỗi compile thật với cảnh báo bị nâng thành lỗi.
- [ ] Đã kiểm thử runtime để phát hiện lỗi cast hoặc contract dữ liệu sau khi compile thành công.
- [ ] Đã ghi lại quyết định tương thích source/binary cho client hoặc plugin độc lập.

## 11. Kết luận trong bối cảnh Java compatibility migration

Lỗi generics và type inference thường chỉ xuất hiện khi biên dịch lại vì compiler kiểm tra source dựa trên generic signature và API hiện tại, trong khi binary cũ thường liên kết theo descriptor sau erasure. Thay đổi dependency, generic bound, overload, target typing, annotation processor hoặc chính sách warning cũng có thể làm kết quả compile khác trước.

Khi điều tra, hãy cố định đầu vào build, đọc diagnostic đầy đủ, so sánh generic signature với descriptor và kiểm tra hành vi dữ liệu sau khi chạy. Cách này giúp xác định đúng lỗi thuộc source contract, binary linkage, compiler configuration hay runtime behavior, đồng thời tránh dùng cast hoặc suppression để che một thay đổi API chưa được hiểu rõ.
