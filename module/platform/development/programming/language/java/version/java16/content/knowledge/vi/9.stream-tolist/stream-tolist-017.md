# Thay `collect()` bằng `toList()` sau khi kiểm tra mọi vị trí sửa kết quả

Từ Java 16, có thể dùng `Stream.toList()` để thu các phần tử thành một `List` không sửa đổi được. Cú pháp ngắn hơn `collect(Collectors.toList())`, nhưng hai cách gọi có hợp đồng khác nhau. `Collectors.toList()` không bảo đảm danh sách kết quả mutable hay unmodifiable; `Stream.toList()` bảo đảm danh sách không sửa đổi được.

Vì vậy, không nên thay hàng loạt `collect(Collectors.toList())` bằng `toList()` chỉ dựa trên việc kiểu trả về đều là `List<T>`. Trước khi thay, hãy rà soát toàn bộ nơi nhận và sử dụng kết quả: lời gọi sửa trực tiếp, phương thức trợ giúp có thể sửa list, API bên ngoài nhận quyền chỉnh sửa, và các thao tác sắp xếp hoặc xóa phần tử. Nếu bất kỳ consumer nào cần mutable list, hãy tạo `ArrayList` một cách tường minh.

## 1. Khác biệt hợp đồng trước khi thay thế

Ví dụ dùng collector:

```java
import java.util.List;
import java.util.stream.Collectors;

List<String> names = List.of("An", "Bình", "Chi").stream()
    .filter(name -> !name.isBlank())
    .collect(Collectors.toList());
```

Ví dụ dùng `Stream.toList()`:

```java
import java.util.List;

List<String> names = List.of("An", "Bình", "Chi").stream()
    .filter(name -> !name.isBlank())
    .toList();
```

Cả hai biểu thức đều có kiểu khai báo `List<String>`, nhưng hợp đồng khác nhau:

| Tiêu chí | `collect(Collectors.toList())` | `toList()` |
| --- | --- | --- |
| Có từ phiên bản | Java 8 | Java 16 |
| Kiểu trả về | `List<T>` | `List<T>` |
| Mutability | Không được API bảo đảm | Unmodifiable theo hợp đồng |
| Lớp triển khai | Không được API bảo đảm | Không được API bảo đảm |
| Gọi mutator | Không được giả định sẽ thành công | Ném `UnsupportedOperationException` |
| Mục đích phù hợp | Thu thập khi chỉ cần hợp đồng `List` chung | Thu thập kết quả để đọc, không cần sửa cấu trúc |

Một số JDK thường triển khai `Collectors.toList()` bằng `ArrayList`, nhưng đó là chi tiết implementation. Nếu chương trình đang dựa vào hành vi đó để sửa danh sách, cần chuyển sang API có hợp đồng mutable rõ ràng trước khi refactor.

## 2. Vì sao thay trực tiếp có thể gây lỗi lúc chạy?

Đoạn mã cũ có thể đang sửa danh sách sau khi thu thập:

```java
import java.util.List;
import java.util.stream.Collectors;

List<String> names = List.of("An", "Bình", "Chi").stream()
    .collect(Collectors.toList());

names.add("Dung");
names.sort(String::compareTo);
```

Nếu chỉ đổi terminal operation:

```java
import java.util.List;

List<String> names = List.of("An", "Bình", "Chi").stream().toList();

names.add("Dung"); // UnsupportedOperationException
```

Mã vẫn có thể biên dịch vì kiểu tĩnh vẫn là `List<String>`. Lỗi chỉ xuất hiện khi chạy tới mutator. Điều này khiến thay đổi có thể vượt qua compile nhưng làm hỏng một luồng nghiệp vụ ít được kiểm thử.

Các mutator cần tìm gồm:

- `add()`, `addAll()` để thêm phần tử.
- `remove()`, `removeAll()`, `retainAll()`, `removeIf()` để xóa phần tử.
- `set()` để thay thế phần tử tại vị trí.
- `clear()` để xóa toàn bộ danh sách.
- `sort()` và `replaceAll()` để thay đổi nội dung hoặc thứ tự.
- `Iterator.remove()`, `ListIterator.add()`, `ListIterator.set()` để sửa qua iterator.
- Mutator trên `subList()` hoặc view được tạo từ danh sách.

Hãy tìm cả lời gọi gián tiếp. Một phương thức nhận `List<T>` có thể gọi `sort()`, `removeIf()` hoặc `add()` bên trong dù chữ ký của nó không thể hiện mutability.

## 3. Rà soát mọi consumer, không chỉ dòng tạo stream

Việc kiểm tra cần theo luồng dữ liệu từ nơi tạo list tới tất cả nơi sử dụng. Ví dụ:

```java
import java.util.List;
import java.util.stream.Collectors;

class NameWorkflow {
    static void run(List<String> source) {
        List<String> result = source.stream()
            .map(String::trim)
            .collect(Collectors.toList());

        printNames(result);
        normalizeInPlace(result);
        saveNames(result);
    }

    private static void printNames(List<String> names) {
        names.forEach(System.out::println); // Chỉ đọc
    }

    private static void normalizeInPlace(List<String> names) {
        names.replaceAll(String::toUpperCase); // Sửa list
    }

    private static void saveNames(List<String> names) {
        System.out.println("Số tên: " + names.size()); // Chỉ đọc
    }
}
```

Trong ví dụ này, `printNames()` và `saveNames()` chỉ đọc. `normalizeInPlace()` sửa từng phần tử qua `replaceAll()`, nên kết quả phải mutable nếu vẫn giữ thiết kế hiện tại.

Sau khi rà soát, có hai hướng:

1. Giữ `normalizeInPlace()` và thu thập vào `ArrayList`.
2. Chuyển `normalizeInPlace()` thành một bước biến đổi trong pipeline trước `toList()`, nếu nghiệp vụ cho phép.

Ví dụ hướng thứ hai:

```java
import java.util.List;

class NameWorkflowWithPipeline {
    static List<String> normalize(List<String> source) {
        return source.stream()
            .map(String::trim)
            .map(String::toUpperCase)
            .toList();
    }
}
```

Khi mọi bước biến đổi được thực hiện trước terminal operation và các consumer sau đó chỉ đọc, `toList()` là lựa chọn phù hợp.

## 4. Kiểm tra phương thức trợ giúp và API bên ngoài

Không phải mọi nơi sửa list đều nằm cạnh dòng `toList()`. Danh sách có thể được truyền qua nhiều lớp:

```java
import java.util.List;

class DisplayExample {
    static void prepareForDisplay(List<String> names) {
        names.sort(String.CASE_INSENSITIVE_ORDER);
        names.add("(kết thúc)");
    }

    static void run() {
        List<String> source = List.of("An", "Bình", "Chi");
        List<String> names = source.stream().toList();
        prepareForDisplay(names); // UnsupportedOperationException
    }
}
```

Chữ ký `prepareForDisplay(List<String>)` không nói rằng phương thức chỉ đọc. Hãy đọc implementation hoặc tài liệu hợp đồng của phương thức. Quy tắc tương tự áp dụng cho:

- Thư viện bên thứ ba nhận list và sắp xếp hoặc chuẩn hóa trực tiếp.
- Framework binding hoặc serializer có thể bổ sung phần tử vào collection được truyền.
- Constructor lưu list và sau đó sửa list đó.
- Callback hoặc listener nhận list và được phép chỉnh sửa.
- Code lưu list vào field mutable rồi cập nhật tại thời điểm khác.

Nếu không kiểm soát được implementation bên ngoài, hãy kiểm tra tài liệu API. Nếu hợp đồng yêu cầu collection mutable, truyền một bản sao mutable thay vì truyền kết quả unmodifiable.

## 5. Chọn `toList()` khi kết quả chỉ cần đọc

Nếu toàn bộ consumer chỉ duyệt, truy vấn hoặc hiển thị kết quả, có thể thay bằng `toList()`:

```java
import java.util.List;

class ReadOnlyNameService {
    static List<String> findNormalizedNames(List<String> source) {
        return source.stream()
            .filter(name -> !name.isBlank())
            .map(String::trim)
            .map(String::toUpperCase)
            .toList();
    }
}
```

Các thao tác đọc như `get()`, `size()`, `contains()`, duyệt bằng `forEach()` hoặc tạo stream tiếp theo vẫn dùng bình thường. Danh sách không sửa đổi được giúp thể hiện rõ rằng consumer không được thay đổi cấu trúc kết quả.

Ví dụ caller chỉ đọc:

```java
import java.util.List;

class ReadOnlyNameClient {
    static void display(List<String> source) {
        List<String> names = ReadOnlyNameService.findNormalizedNames(source);
        names.forEach(System.out::println);
        boolean hasAn = names.contains("AN");
        System.out.println("Có AN: " + hasAn);
    }
}
```

Khi thiết kế phương thức trả về list chỉ đọc, hãy ghi rõ trong Javadoc rằng danh sách không sửa đổi được. Kiểu `List<T>` riêng nó không biểu đạt mutability.

## 6. Giữ mutable bằng `Collectors.toCollection(ArrayList::new)`

Nếu consumer thực sự cần thêm, xóa, thay thế hoặc sắp xếp sau khi thu thập, hãy chỉ định `ArrayList`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;

class EditableNameService {
    static List<String> findNames(List<String> source) {
        return source.stream()
            .map(String::trim)
            .collect(Collectors.toCollection(ArrayList::new));
    }

    static void edit(List<String> source) {
        List<String> editableNames = findNames(source);
        editableNames.add("Dung");
        editableNames.sort(String.CASE_INSENSITIVE_ORDER);
    }
}
```

`Collectors.toCollection(ArrayList::new)` cam kết collection đích là `ArrayList`, có các hành vi mutable được `ArrayList` công bố. Đây là lựa chọn đúng khi mutability là một phần yêu cầu của chương trình.

Nếu đã có kết quả từ `toList()` và chỉ tại một bước sau mới cần chỉnh sửa, tạo bản sao:

```java
import java.util.ArrayList;
import java.util.List;

class EditableCopyExample {
    static List<String> createWorkingCopy(List<String> source) {
        List<String> readOnlyNames = source.stream().toList();
        List<String> editableNames = new ArrayList<>(readOnlyNames);
        editableNames.removeIf(String::isBlank);
        editableNames.add("Dung");
        return editableNames;
    }
}
```

Chọn cách thu thập trực tiếp vào `ArrayList` nếu biết trước kết quả cần mutable. Chọn copy constructor nếu đã có một list và cần tạo một bản làm việc riêng. Đây là bản sao nông; các object mutable bên trong vẫn có thể được chia sẻ.

## 7. Chuyển thao tác sửa list vào pipeline khi phù hợp

Một số đoạn mã sửa list sau khi thu thập chỉ nhằm biến đổi dữ liệu. Nếu có thể diễn đạt cùng logic bằng intermediate operation, pipeline thường rõ ràng hơn và không cần list mutable ở giữa.

Trước:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;

class NormalizeNames {
    static List<String> before(List<String> source) {
        List<String> names = source.stream()
            .collect(Collectors.toCollection(ArrayList::new));

        names.replaceAll(String::trim);
        names.removeIf(String::isBlank);
        names.sort(String.CASE_INSENSITIVE_ORDER);
        return names;
    }
}
```

Sau:

```java
import java.util.List;

class NormalizeNamesWithStream {
    static List<String> after(List<String> source) {
        return source.stream()
            .map(String::trim)
            .filter(name -> !name.isBlank())
            .sorted(String.CASE_INSENSITIVE_ORDER)
            .toList();
    }
}
```

Pipeline sau thể hiện rõ thứ tự biến đổi: chuẩn hóa, lọc, sắp xếp, rồi thu kết quả không sửa đổi được. Chỉ chuyển đổi theo cách này khi các bước có cùng semantics với logic cũ; nếu thao tác sửa list phụ thuộc trạng thái hoặc cần phối hợp với dữ liệu khác, hãy giữ collection mutable và kiểm tra tính tương đương trước khi refactor.

## 8. Kiểm tra khác biệt suy luận generic khi thay terminal operation

Ngoài mutability, `toList()` và `collect(Collectors.toList())` có khác biệt về suy luận kiểu trong một số ngữ cảnh. `Stream.toList()` trả `List<T>` theo đúng kiểu phần tử của stream receiver. Generic method `collect()` có thể suy luận kiểu kết quả theo target type.

```java
import java.util.List;
import java.util.stream.Collectors;

class Animal {}
class Dog extends Animal {}

class GenericMigrationExample {
    static List<Animal> collectAnimals(List<Dog> dogs) {
        return dogs.stream()
            .collect(Collectors.toList()); // Có thể biên dịch nhờ target type inference
    }
}
```

Thay bằng:

```java
import java.util.List;

class Animal {}
class Dog extends Animal {}

class GenericMigrationExample {
    static List<Animal> collectAnimals(List<Dog> dogs) {
        return dogs.stream().toList();
        // Lỗi biên dịch: List<Dog> không phải List<Animal>
    }
}
```

Generic `List<T>` có tính bất biến về tham số kiểu. Nếu cần `List<Animal>`, hãy chuyển kiểu phần tử của stream trước khi thu thập:

```java
import java.util.List;

class Animal {}
class Dog extends Animal {}

class GenericMigrationExample {
    static List<Animal> collectAnimals(List<Dog> dogs) {
        return dogs.stream()
            .<Animal>map(dog -> dog)
            .toList();
    }
}
```

Hoặc dùng `List<? extends Animal>` nếu caller chỉ cần đọc các subtype. Khi thay collector bằng `toList()`, hãy biên dịch lại để phát hiện các trường hợp target type inference thay đổi.

## 9. Kiểm tra chính sách null và thứ tự dữ liệu

Đừng giả định hai API hoàn toàn giống nhau ngoài mutability. Khi refactor, cần xác định rõ dữ liệu đầu vào có thể chứa null không và pipeline có encounter order hay không.

- `Stream.toList()` giữ các phần tử null mà stream phát ra; danh sách vẫn unmodifiable.
- `Collectors.toUnmodifiableList()` từ chối null bằng `NullPointerException`.
- `Collectors.toList()` không cam kết mutability hoặc lớp triển khai cụ thể; nếu code dựa vào hành vi null của implementation hiện tại, hãy xác định chính sách null rõ ràng.
- Với stream có encounter order, `toList()` giữ encounter order. Nếu pipeline gọi `unordered()` hoặc nguồn không có thứ tự, không nên kiểm thử một thứ tự cố định.

Ví dụ nếu muốn loại null trước khi thu thập:

```java
import java.util.List;
import java.util.Objects;

class NullSafeNames {
    static List<String> collect(List<String> source) {
        return source.stream()
            .filter(Objects::nonNull)
            .map(String::trim)
            .toList();
    }
}
```

Nếu muốn từ chối null, hãy xác thực rõ bằng `Objects.requireNonNull()` hoặc dùng collector có hợp đồng từ chối null. Không lọc null nếu null mang ý nghĩa nghiệp vụ cần giữ lại.

## 10. Kiểm tra phiên bản Java mục tiêu

`Stream.toList()` được bổ sung trong Java 16. Dự án phải biên dịch và chạy trên runtime có API này. Nếu sản phẩm vẫn hỗ trợ Java 8 đến Java 15, thay bằng `toList()` sẽ không tương thích với baseline đó.

Hãy kiểm tra:

- Phiên bản JDK dùng để biên dịch.
- `--release` hoặc toolchain được cấu hình trong build.
- Phiên bản Java tối thiểu mà ứng dụng cam kết hỗ trợ khi chạy.
- Các module hoặc thư viện dùng chung có phải tương thích với baseline thấp hơn không.

Ví dụ, mã dùng `Stream.toList()` không thể biên dịch với `javac --release 15`, vì API này chưa tồn tại trong Java 15. Nếu baseline là Java 16 trở lên, có thể dùng API này sau khi hoàn tất kiểm tra consumer.

## 11. Cập nhật test theo hợp đồng mới

Khi thay `collect(Collectors.toList())` bằng `toList()`, các test cũ có thể đang ngầm giả định kết quả mutable. Hãy xem lại mục đích của từng test:

- Nếu phương thức cam kết trả danh sách chỉ đọc, kiểm tra nội dung và xác nhận mutator ném `UnsupportedOperationException`.
- Nếu phương thức cam kết trả danh sách mutable, kiểm tra rằng caller có thể thực hiện thao tác được tài liệu hóa và giữ cách tạo collection mutable.
- Không kiểm tra tên lớp triển khai nội bộ như `ArrayList` nếu hợp đồng không yêu cầu lớp đó.
- Kiểm tra cả đường chạy truyền list cho helper hoặc thư viện có sửa dữ liệu.

Ví dụ JUnit 5 cho kết quả chỉ đọc:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.List;
import org.junit.jupiter.api.Test;

class ReadOnlyNamesTest {
    @Test
    void returnsExpectedUnmodifiableList() {
        List<String> result = List.of("An", "Bình", "Chi").stream().toList();

        assertEquals(List.of("An", "Bình", "Chi"), result);
        assertThrows(UnsupportedOperationException.class,
            () -> result.add("Dung"));
    }
}
```

Nếu test nghiệp vụ cần sửa list, hãy test implementation mutable đã chọn thay vì mong `toList()` cho phép sửa.

## 12. Quy trình migration thực tế

1. **Xác nhận baseline Java:** bảo đảm mọi môi trường build và runtime hỗ trợ Java 16 trở lên.
2. **Tìm tất cả nơi tạo kết quả:** xác định các pipeline đang dùng `collect(Collectors.toList())`.
3. **Theo dấu consumer:** kiểm tra mutator trực tiếp, helper, API bên ngoài, field được lưu và callback.
4. **Phân loại hợp đồng:** chỉ đọc, mutable, hoặc cần một loại collection cụ thể.
5. **Chọn cách thay:** dùng `toList()` cho kết quả chỉ đọc; dùng `toCollection(ArrayList::new)` hoặc copy constructor cho mutable.
6. **Kiểm tra kiểu generic và null:** biên dịch lại, rà soát target type inference, chính sách null và encounter order.
7. **Cập nhật test:** xác minh nội dung, mutability và các consumer quan trọng.
8. **Rà soát import:** bỏ `Collectors` nếu không còn dùng; giữ import nếu vẫn cần collector khác.

| Nhu cầu sau khi thu thập | Lựa chọn |
| --- | --- |
| Chỉ đọc, duyệt hoặc trả snapshot | `stream.toList()` |
| Thêm, xóa, thay thế hoặc sắp xếp sau khi thu thập | `collect(Collectors.toCollection(ArrayList::new))` |
| Đã có kết quả và cần bản làm việc mutable | `new ArrayList<>(result)` |
| Cần collection implementation khác | `collect(Collectors.toCollection(factory))` |
| Cần chạy trên Java trước 16 | Giữ API tương thích với baseline, chẳng hạn collector phù hợp |

## 13. Những điểm cần nhớ

- `toList()` không phải thay thế tương đương về mutability cho `collect(Collectors.toList())`.
- Mã có thể biên dịch nhưng ném `UnsupportedOperationException` tại vị trí sửa list lúc chạy.
- Theo dấu tất cả consumer, kể cả helper và thư viện bên ngoài, trước khi thay terminal operation.
- Nếu chỉ đọc, `toList()` thể hiện hợp đồng unmodifiable rõ ràng.
- Nếu cần mutable, chỉ định `ArrayList` bằng `Collectors.toCollection(ArrayList::new)` hoặc tạo bản sao.
- Kiểm tra generic target type inference, null policy, encounter order và Java baseline.
- Cập nhật test theo hợp đồng mà phương thức thực sự công bố.

Hãy quyết định theo cách kết quả được sử dụng sau khi thu thập. Chỉ thay bằng `toList()` khi mọi consumer đều phù hợp với danh sách unmodifiable. Nếu có bất kỳ nơi nào cần sửa, hãy giữ một collection mutable có hợp đồng rõ ràng hoặc chuyển thao tác biến đổi vào pipeline trước khi thu thập.

## Tài liệu tham khảo

- [Stream.toList() – Java SE 16 API](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/util/stream/Stream.html#toList())
- [Stream.toList() – Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Stream.html#toList())
- [Collectors.toList() và toCollection() – Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Collectors.html)
- [ArrayList – Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ArrayList.html)
- [Java Language Specification, §4.10 – Subtyping](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-4.html#jls-4.10)
