# Kiểm thử cùng một hợp đồng trên nhiều cách triển khai

Khi một interface có nhiều lớp triển khai, mỗi lớp có thể dùng cấu trúc dữ liệu hoặc thuật toán khác nhau nhưng vẫn phải tuân thủ cùng một hành vi công khai. **Contract test** là bộ kiểm thử mô tả hành vi bắt buộc của abstraction và chạy bộ kiểm thử đó với từng implementation. Cách này giúp phát hiện một lớp triển khai vi phạm hợp đồng mà không cần viết lại cùng một nhóm kiểm thử cho từng lớp.

Ví dụ, một interface lưu trữ cặp khóa–giá trị có thể được triển khai bằng `HashMap` hoặc `TreeMap`. Cả hai cách triển khai đều phải cho cùng kết quả khi thêm, đọc, ghi đè và xóa dữ liệu, dù cấu trúc nội bộ khác nhau.

## 1. Hợp đồng là gì?

Hợp đồng là tập quy tắc mà người gọi được phép dựa vào khi sử dụng một interface. Hợp đồng thường xác định:

- **Tiền điều kiện:** dữ liệu đầu vào được chấp nhận hay bị từ chối.
- **Hậu điều kiện:** điều gì phải đúng sau khi một thao tác hoàn tất.
- **Bất biến:** điều gì luôn đúng về trạng thái của đối tượng.
- **Hành vi biên:** kết quả khi khóa không tồn tại, collection rỗng, đầu vào sai hoặc thao tác lặp lại.
- **Lỗi được quy định:** loại lỗi mà caller có thể trông đợi với đầu vào không hợp lệ.

Một interface Java chỉ khai báo chữ ký phương thức chưa chắc đã diễn đạt đầy đủ hợp đồng. Javadoc, quy ước API và kiểm thử cần làm rõ những điểm như giá trị trả về khi không tìm thấy dữ liệu, chính sách `null`, ý nghĩa của `false` khi xóa, hoặc việc gọi lại thao tác có tạo thêm phần tử hay không.

Contract test kiểm tra **hành vi quan sát được từ bên ngoài**. Nó không nên phụ thuộc vào tên trường, loại collection nội bộ, thứ tự duyệt nếu hợp đồng không bảo đảm thứ tự, hoặc cách thuật toán được triển khai.

## 2. Ví dụ về hợp đồng dùng chung

Giả sử ứng dụng cần một kho lưu trữ đơn giản:

| Thao tác | Quy tắc của hợp đồng |
| --- | --- |
| Tạo kho mới | `size()` bằng `0`. |
| `put(key, value)` | Cả khóa và giá trị phải khác `null`; lưu giá trị cho khóa. |
| Ghi đè khóa đã có | Giá trị mới thay thế giá trị cũ; số khóa không tăng. |
| `get(key)` | Trả về `Optional` có giá trị nếu khóa tồn tại, nếu không thì `Optional.empty()`. |
| `remove(key)` với khóa tồn tại | Trả về `true` và xóa khóa. |
| `remove(key)` với khóa không tồn tại | Trả về `false`, trạng thái kho không đổi. |
| Đưa `null` vào vị trí khóa hoặc giá trị | Ném `NullPointerException` theo chính sách đã chọn. |

Trong ví dụ này, hợp đồng cố ý không quy định thứ tự các khóa. Vì vậy, implementation dùng `TreeMap` không được coi là đúng hơn implementation dùng `HashMap` chỉ vì nó sắp xếp khóa. Nếu ứng dụng cần thứ tự, hãy đưa yêu cầu về thứ tự vào hợp đồng một cách tường minh và kiểm thử nó.

## 3. Chương trình Java 17+ hoàn chỉnh

Ví dụ dưới đây chạy được mà không cần thư viện kiểm thử bên ngoài. Phương thức `runContract` chứa một bộ kiểm tra duy nhất. Chương trình chạy bộ đó với hai implementation độc lập: `HashMapStore` và `TreeMapStore`.

Lưu toàn bộ mã vào tệp `ContractTestDemo.java`:

```java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.TreeMap;
import java.util.function.Supplier;

public class ContractTestDemo {
    public static void main(String[] args) {
        runContract("HashMapStore", HashMapStore::new);
        runContract("TreeMapStore", TreeMapStore::new);
        System.out.println("All contract checks passed.");
    }

    private static void runContract(
            String name, Supplier<KeyValueStore> factory) {
        // Mỗi implementation bắt đầu bằng một đối tượng mới.
        KeyValueStore store = factory.get();

        require(store.size() == 0, "new store must be empty");
        require(store.get("missing").isEmpty(),
                "missing key must return Optional.empty");

        store.put("alpha", "one");
        require(store.get("alpha").equals(Optional.of("one")),
                "get must return the stored value");
        require(store.size() == 1,
                "put must add one key");

        store.put("alpha", "two");
        require(store.get("alpha").equals(Optional.of("two")),
                "put must replace the existing value");
        require(store.size() == 1,
                "overwriting a key must not increase size");

        store.put("beta", "value");
        require(store.size() == 2,
                "a different key must add one entry");

        require(store.remove("alpha"),
                "removing an existing key must return true");
        require(store.get("alpha").isEmpty(),
                "removed key must no longer be present");
        require(store.size() == 1,
                "removing a key must decrease size");

        require(!store.remove("missing"),
                "removing a missing key must return false");
        require(store.size() == 1,
                "removing a missing key must not change size");

        expectNullPointer(
                () -> store.put(null, "value"),
                "null key must be rejected");
        expectNullPointer(
                () -> store.put("key", null),
                "null value must be rejected");
        expectNullPointer(
                () -> store.get(null),
                "null lookup key must be rejected");
        expectNullPointer(
                () -> store.remove(null),
                "null removal key must be rejected");

        System.out.println("PASS " + name);
    }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    private static void expectNullPointer(
            Runnable action, String message) {
        try {
            action.run();
        } catch (NullPointerException expected) {
            return;
        }
        throw new AssertionError(message);
    }

    interface KeyValueStore {
        void put(String key, String value);
        Optional<String> get(String key);
        boolean remove(String key);
        int size();
    }

    static final class HashMapStore implements KeyValueStore {
        private final Map<String, String> data = new HashMap<>();

        @Override
        public void put(String key, String value) {
            Objects.requireNonNull(key, "key");
            Objects.requireNonNull(value, "value");
            data.put(key, value);
        }

        @Override
        public Optional<String> get(String key) {
            Objects.requireNonNull(key, "key");
            return Optional.ofNullable(data.get(key));
        }

        @Override
        public boolean remove(String key) {
            Objects.requireNonNull(key, "key");
            return data.remove(key) != null;
        }

        @Override
        public int size() {
            return data.size();
        }
    }

    static final class TreeMapStore implements KeyValueStore {
        private final Map<String, String> data = new TreeMap<>();

        @Override
        public void put(String key, String value) {
            Objects.requireNonNull(key, "key");
            Objects.requireNonNull(value, "value");
            data.put(key, value);
        }

        @Override
        public Optional<String> get(String key) {
            Objects.requireNonNull(key, "key");
            return Optional.ofNullable(data.get(key));
        }

        @Override
        public boolean remove(String key) {
            Objects.requireNonNull(key, "key");
            return data.remove(key) != null;
        }

        @Override
        public int size() {
            return data.size();
        }
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```text
javac --release 17 ContractTestDemo.java
java ContractTestDemo
```

Đầu ra chuẩn của chương trình:

```text
PASS HashMapStore
PASS TreeMapStore
All contract checks passed.
```

Nếu một implementation vi phạm một quy tắc, `require` hoặc `expectNullPointer` ném `AssertionError`; chương trình không in dòng `PASS` cho implementation đó và kết thúc bằng lỗi. Vì vậy, dòng `PASS` chỉ xuất hiện sau khi toàn bộ các kiểm tra của implementation đã hoàn thành.

## 4. Vì sao cùng một bộ kiểm thử có giá trị?

`runContract` không kiểm tra lớp đang dùng `HashMap` hay `TreeMap`. Nó chỉ gọi các phương thức công khai của `KeyValueStore` và xác nhận kết quả theo hợp đồng.

Điều này mang lại ba lợi ích:

1. **Nhất quán:** mọi implementation đều phải đáp ứng cùng một nhóm hành vi.
2. **Khả năng mở rộng:** khi thêm implementation thứ ba, chỉ cần cung cấp factory và chạy lại contract test.
3. **Bảo trì tập trung:** khi hợp đồng thay đổi có chủ đích, cập nhật một bộ kiểm thử chung rồi chạy lại trên tất cả implementation.

Tuy nhiên, contract test không thay thế mọi kiểm thử khác. Mỗi implementation vẫn có thể cần kiểm thử riêng cho thuật toán, hiệu năng, giới hạn dung lượng, đồng bộ luồng hoặc đặc tính bổ sung không nằm trong interface.

## 5. Tổ chức contract test với JUnit 5

Trong dự án thực tế, JUnit 5 giúp mỗi quy tắc trở thành một test độc lập. Một mẫu thông dụng là đặt các test chung trong lớp trừu tượng, rồi để lớp test cụ thể cung cấp implementation thông qua factory method.

Ví dụ sau giả định interface và hai implementation được tách thành các lớp production trong cùng package. Lớp kiểm thử trừu tượng có thể nằm trong `src/test/java`:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

abstract class KeyValueStoreContractTest {
    protected abstract KeyValueStore newStore();

    @Test
    void newStoreIsEmpty() {
        assertEquals(0, newStore().size());
    }

    @Test
    void missingKeyReturnsEmpty() {
        assertTrue(newStore().get("missing").isEmpty());
    }

    @Test
    void storedValueCanBeRead() {
        KeyValueStore store = newStore();
        store.put("alpha", "one");

        assertEquals("one", store.get("alpha").orElseThrow());
    }

    @Test
    void puttingExistingKeyReplacesValue() {
        KeyValueStore store = newStore();
        store.put("alpha", "one");
        store.put("alpha", "two");

        assertEquals("two", store.get("alpha").orElseThrow());
        assertEquals(1, store.size());
    }

    @Test
    void removingExistingKeyReturnsTrue() {
        KeyValueStore store = newStore();
        store.put("alpha", "one");

        assertTrue(store.remove("alpha"));
        assertTrue(store.get("alpha").isEmpty());
    }

    @Test
    void removingMissingKeyReturnsFalse() {
        KeyValueStore store = newStore();

        assertFalse(store.remove("missing"));
        assertEquals(0, store.size());
    }

    @Test
    void nullKeyIsRejected() {
        assertThrows(
                NullPointerException.class,
                () -> newStore().get(null));
    }

    @Test
    void nullValueIsRejected() {
        assertThrows(
                NullPointerException.class,
                () -> newStore().put("alpha", null));
    }
}
```

Sau đó, tạo một lớp test cụ thể cho từng implementation:

```java
import org.junit.jupiter.api.Test;

class HashMapKeyValueStoreTest extends KeyValueStoreContractTest {
    @Override
    protected KeyValueStore newStore() {
        return new HashMapKeyValueStore();
    }
}

class TreeKeyValueStoreTest extends KeyValueStoreContractTest {
    @Override
    protected KeyValueStore newStore() {
        return new TreeKeyValueStore();
    }
}
```

Đây là cấu trúc minh họa; trong dự án, mỗi lớp test top-level thường được đặt trong tệp riêng có tên tương ứng. `HashMapKeyValueStore` và `TreeKeyValueStore` là tên ví dụ cho hai implementation production.

JUnit Jupiter nhận các phương thức `@Test` kế thừa từ lớp cha trừu tượng khi chạy lớp con cụ thể. Do đó, cả hai lớp test đều chạy cùng các quy tắc mà không phải sao chép phần thân test. Factory `newStore()` tạo đối tượng mới cho từng test, tránh trạng thái của test trước ảnh hưởng đến test sau.

Với Maven, cần khai báo JUnit Jupiter ở phạm vi `test` và một phiên bản Maven Surefire hỗ trợ JUnit Platform. Sau đó có thể chạy:

```text
mvn test
```

Bộ kiểm thử JUnit phía trên minh họa các quy tắc cốt lõi. Hãy bổ sung các test cho mọi cam kết còn lại của hợp đồng, chẳng hạn `size()` sau mỗi thao tác và hành vi khi xóa khóa vừa được ghi đè.

## 6. Phân biệt contract test và test riêng của implementation

Dùng contract test cho những gì mọi implementation bắt buộc phải làm giống nhau. Dùng test riêng cho các đặc tính được công bố riêng của một implementation.

| Loại kiểm thử | Ví dụ | Nên đặt ở đâu |
| --- | --- | --- |
| Hợp đồng chung | Ghi rồi đọc trả lại đúng giá trị. | Bộ contract test dùng chung. |
| Hợp đồng chung | Khóa không tồn tại trả về `Optional.empty()`. | Bộ contract test dùng chung. |
| Hợp đồng chung | Ghi đè không tạo thêm một khóa. | Bộ contract test dùng chung. |
| Đặc tính riêng | `TreeMap` trả khóa theo thứ tự sắp xếp. | Test riêng cho implementation, nếu hành vi này được cung cấp. |
| Đặc tính riêng | Cache phải loại bỏ mục theo chính sách LRU. | Test riêng cho cache. |
| Đặc tính riêng | Implementation có giới hạn dung lượng hoặc chính sách retry. | Test riêng cho tính năng đó. |
| Tích hợp | Kết nối cơ sở dữ liệu, transaction hoặc serialization hoạt động đúng. | Test tích hợp phù hợp với hạ tầng thực tế. |

Đừng thêm yêu cầu sắp xếp khóa vào contract chỉ vì implementation hiện tại dùng `TreeMap`. Làm như vậy sẽ ép tất cả implementation tuân theo một đặc tính có thể không cần thiết. Ngược lại, nếu caller được quyền dựa vào thứ tự, thứ tự phải được ghi rõ trong hợp đồng và mọi implementation phải đáp ứng nó.

## 7. Các lỗi thiết kế và kiểm thử thường gặp

**Sao chép test cho từng lớp.** Khi test được sao chép, một implementation dễ bị bỏ sót khi hợp đồng thay đổi. Đặt quy tắc chung trong một contract suite và dùng factory để cung cấp các implementation.

**Kiểm tra chi tiết nội bộ.** Một test yêu cầu implementation phải có trường tên `map`, hoặc phải dùng đúng `HashMap`, sẽ thất bại khi có cách triển khai tương đương nhưng hợp lệ. Hãy kiểm tra kết quả qua interface.

**Đưa giả định không có trong hợp đồng vào test.** Ví dụ, so sánh thứ tự khóa khi API không bảo đảm thứ tự sẽ tạo ra test mong manh. Chỉ kiểm thử những hành vi đã cam kết.

**Không tạo trạng thái mới cho mỗi test.** Nếu nhiều test chia sẻ một instance, thứ tự chạy có thể ảnh hưởng kết quả. Mỗi test nên tự tạo đối tượng hoặc dùng fixture có cơ chế đặt lại trạng thái rõ ràng.

**Chỉ kiểm tra đường đi thành công.** Các lỗi phổ biến xuất hiện ở khóa không tồn tại, dữ liệu `null`, thao tác lặp lại và trạng thái rỗng. Đưa các trường hợp biên vào hợp đồng khi chúng ảnh hưởng đến caller.

**Dùng một test suite quá rộng cho các API khác nhau.** Nếu hai implementation có hành vi khác nhau một cách có chủ đích, đừng ép chúng vào cùng một hợp đồng sai lệch. Hãy tách abstraction hoặc chia contract thành các nhóm tính năng mà mỗi implementation cam kết hỗ trợ.

**Dùng mock thay cho implementation thật trong contract test.** Mục tiêu của contract test là xác nhận implementation thực sự tuân thủ hợp đồng. Mock có thể hữu ích để kiểm thử caller, nhưng không chứng minh lớp triển khai thật đáp ứng quy tắc.

**Cho rằng test thành công chứng minh mọi hành vi đều đúng.** Contract test chỉ bao phủ các quy tắc và tình huống đã viết. Nó không tự chứng minh tính đúng đắn hình thức, an toàn luồng, hiệu năng hay mọi đầu vào có thể có.

## 8. Khi contract test thất bại, điều tra thế nào?

1. Xác định implementation nào thất bại và quy tắc hợp đồng nào bị vi phạm.
2. Kiểm tra test có dựa vào hành vi đã được quy định hay đang giả định một chi tiết triển khai.
3. Nếu test diễn đạt đúng hợp đồng, sửa implementation hoặc xác định rõ lỗi của nó.
4. Nếu hợp đồng mơ hồ, quyết định hành vi API cần cam kết rồi cập nhật tài liệu và test một cách nhất quán.
5. Chạy lại contract suite trên tất cả implementation, không chỉ lớp vừa sửa.
6. Chạy thêm test riêng hoặc test tích hợp cho các rủi ro mà hợp đồng chung không bao phủ.

Không nên xóa một assertion chỉ để làm bộ test xanh. Trước tiên hãy xác định assertion đó có đại diện cho một cam kết thật của API hay không.

## 9. Checklist khi thêm implementation mới

- Đọc hợp đồng của interface và xác định rõ tiền điều kiện, kết quả trả về, lỗi và các trường hợp biên.
- Xác nhận implementation mới thực sự đáp ứng cùng abstraction; không bỏ qua quy tắc chỉ vì lớp biên dịch được.
- Chạy toàn bộ contract suite trên implementation mới.
- Đảm bảo mỗi test có trạng thái ban đầu độc lập và không phụ thuộc thứ tự chạy.
- Giữ các kiểm tra về cấu trúc nội bộ, hiệu năng và tính năng riêng trong test phù hợp của implementation.
- Khi thêm hoặc đổi một quy tắc công khai, cập nhật hợp đồng và chạy lại suite cho mọi implementation.
- Khi một implementation không thể đáp ứng hợp đồng, xem xét lại abstraction hoặc tạo interface riêng cho khả năng khác biệt, thay vì âm thầm thay đổi ý nghĩa của một phương thức.

Contract test làm cho interface trở thành một cam kết có thể kiểm chứng. Khi cùng một bộ kiểm thử chạy qua mọi implementation, nhóm phát triển có thể thay đổi cấu trúc bên trong với độ tin cậy cao hơn mà vẫn giữ nguyên hành vi mà caller đã được hứa hẹn.
