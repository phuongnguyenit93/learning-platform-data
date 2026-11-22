# Kiểm thử các cách thực hiện cùng một giao diện trong Java

## 1. Vấn đề cần giải quyết

Trong lập trình hướng đối tượng, một **interface** có thể có nhiều lớp triển khai. Ví dụ, giao diện tập hợp số nguyên có thể được triển khai bằng HashSet, TreeSet hoặc một cấu trúc dữ liệu tự viết. Các lớp đó dùng thuật toán khác nhau, nhưng người gọi phải nhận được **cùng hành vi đã cam kết** qua interface.

Nếu chỉ kiểm thử từng lớp bằng những bộ test viết riêng, ta dễ bỏ sót một trường hợp ở một implementation hoặc vô tình chấp nhận hai cách xử lý mâu thuẫn nhau. **Contract test (kiểm thử hợp đồng)** giải quyết vấn đề đó: định nghĩa một bộ kiểm thử hành vi chung rồi chạy nguyên bộ trên mọi implementation.

Mục tiêu của bài:
- Phân biệt **hợp đồng quan sát được** với chi tiết hiện thực bên trong.
- Viết test dùng chung qua một **factory** tạo implementation.
- Kiểm thử trạng thái, kết quả trả về, ca biên và sự độc lập giữa các đối tượng.
- Biết nơi cần thêm test riêng, ngoài bộ test hợp đồng chung.

## 2. Xác định hợp đồng trước khi viết test

Ta tạo giao diện IntSet lưu các số nguyên, không cho phần tử trùng. Hợp đồng được quyết định ở cấp giao diện, nên HashIntSet và TreeIntSet đều phải tuân thủ.

| Thao tác | Hợp đồng chung có thể kiểm thử |
| --- | --- |
| new IntSet | Tập hợp ban đầu rỗng; size() = 0. |
| add(x) | Trả true nếu thêm mới; trả false nếu x đã tồn tại; không tăng size khi thêm trùng. |
| contains(x) | Cho biết x hiện có trong tập hay không, không thay đổi trạng thái. |
| remove(x) | Trả true nếu x đã bị xóa; trả false nếu không tìm thấy; cập nhật size chính xác. |
| size() | Luôn bằng số phần tử **phân biệt** hiện có; không âm. |
| Miền giá trị | Cho phép mọi giá trị int, kể cả số âm, 0, MIN_VALUE và MAX_VALUE. |
| Độc lập đối tượng | Thao tác trên một đối tượng không làm thay đổi đối tượng mới khác. |

**Không đưa vào hợp đồng** thứ tự duyệt phần tử, loại cây/bảng băm, thời gian thực thi hay chi tiết bộ nhớ vì interface hiện tại không công bố các đặc tính đó. Không viết assert dựa trên những điều chưa được cam kết.

Luồng kiểm thử:

~~~mermaid
flowchart TD
  A["Hợp đồng IntSet"] --> B["Bộ contract test JUnit 5"]
  B --> C["Factory: HashIntSet"]
  B --> D["Factory: TreeIntSet"]
  C --> E["Cùng các trường hợp kiểm thử"]
  D --> E
  E --> F{"Mọi implementation đều đạt?"}
  F -->|Có| G["Phù hợp với hợp đồng đã kiểm"]
  F -->|Không| H["Xác định implementation và ca vi phạm"]
~~~

## 3. Ví dụ chạy được: Java 17 + Maven + JUnit 5

Cấu trúc dự án:

~~~text
oop-contract-test/
├── pom.xml
└── src/
    ├── main/java/example/IntSet.java
    └── test/java/example/IntSetContractTest.java
~~~

### 3.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example</groupId>
  <artifactId>oop-contract-test</artifactId>
  <version>1.0-SNAPSHOT</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.junit.jupiter</groupId>
      <artifactId>junit-jupiter</artifactId>
      <version>5.11.4</version>
      <scope>test</scope>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-surefire-plugin</artifactId>
        <version>3.5.2</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

### 3.2. src/main/java/example/IntSet.java

~~~java
package example;

import java.util.HashSet;
import java.util.Set;
import java.util.TreeSet;

/**
 * Tập hợp các giá trị int phân biệt.
 * Mỗi đối tượng mới phải rỗng; mọi giá trị int đều hợp lệ.
 */
public interface IntSet {
    /** true chỉ khi giá trị được thêm mới. */
    boolean add(int value);

    /** Không làm thay đổi tập hợp. */
    boolean contains(int value);

    /** true chỉ khi phần tử có tồn tại và đã bị xóa. */
    boolean remove(int value);

    /** Số phần tử phân biệt hiện đang có. */
    int size();
}

final class HashIntSet implements IntSet {
    private final Set<Integer> values = new HashSet<>();

    @Override
    public boolean add(int value) {
        return values.add(value);
    }

    @Override
    public boolean contains(int value) {
        return values.contains(value);
    }

    @Override
    public boolean remove(int value) {
        return values.remove(value);
    }

    @Override
    public int size() {
        return values.size();
    }
}

final class TreeIntSet implements IntSet {
    private final Set<Integer> values = new TreeSet<>();

    @Override
    public boolean add(int value) {
        return values.add(value);
    }

    @Override
    public boolean contains(int value) {
        return values.contains(value);
    }

    @Override
    public boolean remove(int value) {
        return values.remove(value);
    }

    @Override
    public int size() {
        return values.size();
    }
}
~~~

Để ví dụ gọn và biên dịch được từ một tệp, hai lớp triển khai ở đây có phạm vi package-private (không khai báo public). Trong ứng dụng thực tế, có thể tách mỗi lớp sang một tệp.

### 3.3. src/test/java/example/IntSetContractTest.java

~~~java
package example;

import static org.junit.jupiter.api.Assertions.*;

import java.util.function.Supplier;
import java.util.stream.Stream;

import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;

class IntSetContractTest {

    // Mỗi test nhận một nhà máy tạo đối tượng mới.
    static Stream<Arguments> variants() {
        return Stream.of(
            Arguments.of("HashIntSet", (Supplier<IntSet>) HashIntSet::new),
            Arguments.of("TreeIntSet", (Supplier<IntSet>) TreeIntSet::new)
        );
    }

    @ParameterizedTest(name = "{0}: tap moi phai rong")
    @MethodSource("variants")
    void initiallyEmpty(String name, Supplier<IntSet> factory) {
        IntSet set = factory.get();

        assertEquals(0, set.size());
        assertFalse(set.contains(5));
        assertFalse(set.remove(5));
        assertEquals(0, set.size());
    }

    @ParameterizedTest(name = "{0}: them trung khong tang size")
    @MethodSource("variants")
    void addIsIdempotent(String name, Supplier<IntSet> factory) {
        IntSet set = factory.get();

        assertTrue(set.add(7));
        assertTrue(set.contains(7));
        assertEquals(1, set.size());

        assertFalse(set.add(7));
        assertEquals(1, set.size());
    }

    @ParameterizedTest(name = "{0}: xoa va them lai")
    @MethodSource("variants")
    void removeAndReAdd(String name, Supplier<IntSet> factory) {
        IntSet set = factory.get();

        assertTrue(set.add(10));
        assertTrue(set.add(20));
        assertTrue(set.remove(10));
        assertFalse(set.contains(10));
        assertTrue(set.contains(20));
        assertEquals(1, set.size());

        assertFalse(set.remove(10));
        assertTrue(set.add(10));
        assertEquals(2, set.size());
    }

    @ParameterizedTest(name = "{0}: gia tri bien va so am")
    @MethodSource("variants")
    void acceptsAllIntValues(String name, Supplier<IntSet> factory) {
        IntSet set = factory.get();
        int[] inputs = {
            Integer.MIN_VALUE, -1, 0, Integer.MAX_VALUE
        };

        for (int x : inputs) {
            assertTrue(set.add(x));
            assertTrue(set.contains(x));
        }
        assertEquals(inputs.length, set.size());

        for (int x : inputs) {
            assertFalse(set.add(x));
        }
        assertEquals(inputs.length, set.size());
    }

    @ParameterizedTest(name = "{0}: cac doi tuong doc lap")
    @MethodSource("variants")
    void independentInstances(String name, Supplier<IntSet> factory) {
        IntSet first = factory.get();
        IntSet second = factory.get();

        assertTrue(first.add(42));
        assertTrue(first.contains(42));
        assertFalse(second.contains(42));
        assertEquals(0, second.size());
    }
}
~~~

Lưu ý cách vận hành:
1. Phương thức variants() liệt kê **tên implementation + Supplier**.
2. JUnit 5 gọi **mỗi phương thức @ParameterizedTest một lần cho từng dòng dữ liệu** từ @MethodSource.
3. Trong mỗi lần gọi, factory.get() sinh **đối tượng mới**; tránh việc test trước làm bẩn trạng thái test sau.
4. Cùng 5 trường hợp chạy trên 2 implementation: dự kiến **10 lượt kiểm thử**. Tên implementation xuất hiện trong kết quả khi một trường hợp thất bại.

Chạy tại thư mục chứa pom.xml:

~~~bash
mvn test
~~~

Với các lớp như mã nguồn trên, Maven Surefire phải kết thúc thành công với 10 lượt test không thất bại. Nếu một implementation trả kết quả khác hợp đồng, JUnit chỉ ra ca và biến thể liên quan.

## 4. Vì sao bộ test chung có giá trị?

Giả sử một implementation lỗi viết add như sau:

~~~java
@Override
public boolean add(int value) {
    values.add(value);
    return true; // Sai khi value đã tồn tại!
}
~~~

Bộ kiểm thử addIsIdempotent sẽ thất bại ở lần add(7) thứ hai, dù size vẫn bằng 1. Đây là lỗi **hợp đồng về giá trị trả về**, không phải lỗi cấu trúc lưu trữ.

Một lỗi khác: dùng chung biến static để lưu tập hợp giữa các đối tượng. Kiểm thử independentInstances sẽ bắt được việc hai đối tượng tác động lẫn nhau. Viết test chỉ cho từng thao tác riêng lẻ có thể bỏ sót lỗi dạng này.

| Trường hợp | Chỉ kiểm tra kết quả cuối | Contract test tốt hơn |
| --- | --- | --- |
| add cùng giá trị hai lần | Có thể vẫn thấy size = 1. | Kiểm tra cả hai giá trị boolean và size. |
| remove phần tử không tồn tại | Có thể không phát hiện lỗi trả về. | Yêu cầu false và trạng thái không đổi. |
| Thêm MIN_VALUE | Dễ bị quên trong bộ test thông thường. | Kiểm tra miền int đã công bố. |
| Hai instance cùng tồn tại | Dễ bỏ qua nếu chỉ tạo một object. | Bảo đảm không dùng trạng thái chia sẻ ngoài hợp đồng. |

## 5. Phân biệt contract test với test riêng

**Contract test** bảo vệ những gì mọi implementation đều phải làm: đầu vào hợp lệ, kết quả, ngoại lệ đã cam kết, bất biến trạng thái, hành vi khi gọi nhiều lần.

**Implementation-specific test** kiểm tra những yêu cầu chỉ một implementation có. Chẳng hạn một lớp dùng cơ sở dữ liệu còn cần test transaction, rollback, mapping và kết nối thật. Một lớp cache còn cần test TTL, eviction và thread-safety **nếu những đặc tính này thuộc yêu cầu của lớp**.

**Integration test** dùng cấu hình thật của hệ thống để kiểm chứng adapter kết nối tài nguyên bên ngoài. Contract test chạy trên fake hoặc bộ nhớ không đủ để khẳng định JDBC implementation hoạt động với database thật.

Ví dụ nếu giao diện Repository có các triển khai InMemoryRepository và JdbcRepository, có thể tái sử dụng bộ contract test bằng factory:

~~~java
// Ý tưởng tổ chức, không phải mã độc lập của dự án IntSet.
abstract class RepositoryContractTest {
    protected abstract Repository newRepository();

    // Các @Test chỉ gọi hàm trên Repository,
    // không phụ thuộc InMemoryRepository hay JdbcRepository.
}
~~~

Cần bảo đảm setup/cleanup tài nguyên (tạo schema, seed dữ liệu, rollback hoặc xóa theo test), không để test chạy song song cùng đụng dữ liệu. Dùng implementation thật trong CI để tránh tình huống fake vượt qua test nhưng SQL có hành vi khác.

## 6. Nguyên tắc viết hợp đồng đáng tin cậy

- **Xác định hành vi trước:** tài liệu interface/Javadoc và yêu cầu nghiệp vụ là nguồn quyết định. Hai implementation cùng trả một kết quả sai không làm kết quả đó thành đúng.
- **Kiểm tra từ góc nhìn người gọi:** gọi hàm public qua biến kiểu interface; tránh đọc các trường private hoặc ép kiểu về implementation chỉ để xác nhận cấu trúc nội bộ.
- **Giữ mỗi test độc lập:** tạo fixture mới cho từng ca, kiểm soát đồng hồ, random seed, thứ tự test và tài nguyên bên ngoài khi có liên quan.
- **Kiểm thử chuỗi thao tác:** thêm → tìm → thêm trùng → xóa → thêm lại thường phát hiện lỗi trạng thái tốt hơn chỉ kiểm thử một lệnh.
- **Bao phủ phân vùng và biên:** rỗng, tồn tại/không tồn tại, trùng, số âm, MIN_VALUE/MAX_VALUE; đối với interface nhận tham chiếu còn phải định nghĩa xử lý null.
- **Kiểm tra ngoại lệ có chủ đích:** nếu hợp đồng yêu cầu IllegalArgumentException cho đầu vào không hợp lệ, dùng assertThrows trên *mọi* implementation; không tự suy đoán ngoại lệ từ một lớp cụ thể.
- **Tránh assert chi tiết không hứa hẹn:** không so sánh thứ tự duyệt HashSet với TreeSet; nếu thứ tự là yêu cầu, phải ghi vào interface rồi test đúng yêu cầu đó.
- **Không lạm dụng mock:** mock hữu ích để cô lập dependency khi test một consumer; nó không thay thế được việc kiểm chứng implementation thật có thỏa hợp đồng.
- **Thêm implementation mới = đăng ký vào cùng test:** với ví dụ này, có thể tạo LinkedHashIntSet và bổ sung một Arguments.of vào variants(); không cần nhân bản năm phương thức test.
- **Hiểu giới hạn:** bộ test chung chứng minh những ca đã kiểm được đáp ứng, không phải chứng minh mọi đầu vào và mọi đặc tính phi chức năng đều đúng.

## 7. Thực hành tự kiểm tra

1. Thêm implementation LinkedHashIntSet dùng LinkedHashSet<Integer>, khai báo implements IntSet. Đăng ký factory vào variants() và chạy lại. Dự kiến 15 lượt test.
2. Cố tình sửa remove() để luôn trả false, chạy test xem trường hợp nào bắt lỗi; khôi phục mã đúng.
3. Bổ sung contract test cho chuỗi add(3), add(4), remove(3), add(3); xác nhận size và contains ở từng bước.
4. Nếu bổ sung phương thức values() trả Collection<Integer>, hãy quyết định rõ có cam kết thứ tự không. Sau đó viết test đúng hợp đồng, tránh phụ thuộc ngẫu nhiên vào cấu trúc dữ liệu.

**Tiêu chí hoàn thành:** bất cứ lớp nào khai báo implements IntSet đều có thể chạy cùng bộ test, và mỗi thất bại phải chỉ ra được hành vi nào của hợp đồng bị vi phạm.