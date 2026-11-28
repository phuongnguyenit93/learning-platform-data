# Khả năng không cho phép sửa đổi và bất biến của phần tử

Các tập hợp khởi tạo trễ trong Java 26/27 có thể ngăn mã gọi thêm, xóa hoặc thay thế phần tử, đồng thời chỉ tính giá trị khi phần tử được truy cập lần đầu. Tuy nhiên, **không cho phép sửa đổi tập hợp (unmodifiable) không đồng nghĩa với bất biến sâu (immutable)**. Nếu phần tử bên trong là đối tượng có thể thay đổi, trạng thái của đối tượng đó vẫn có thể đổi dù cấu trúc List, Map hoặc Set không cho phép cập nhật.

Điểm cần nắm khi dùng Lazy Collections là tách hai lớp bảo đảm: tập hợp giữ ổn định số lượng, khóa và vị trí phần tử; còn tính bất biến của từng đối tượng phụ thuộc vào kiểu phần tử và cách thiết kế đối tượng đó. Bài này tập trung vào khác biệt ấy, cách kiểm chứng bằng Java 27 và những giới hạn cần biết trước khi chia sẻ dữ liệu giữa các thành phần hoặc luồng.

## 1. Trạng thái API theo phiên bản

Lazy Collections được đưa vào cùng hướng phát triển Lazy Constants. Các factory tạo tập hợp khởi tạo trễ là **preview API**, chưa phải API Java SE ổn định.

| Release | API lazy collection | Trạng thái |
|---|---|---|
| Java 26 | `List.ofLazy(int, IntFunction)` | Preview |
| Java 26 | `Map.ofLazy(Set, Function)` | Preview |
| Java 26 | `Set.ofLazy(...)` | Chưa có |
| Java 27 | `List.ofLazy(int, IntFunction)` | Preview, tiếp tục có |
| Java 27 | `Map.ofLazy(Set, Function)` | Preview, tiếp tục có |
| Java 27 | `Set.ofLazy(Set, Predicate)` | Preview, được bổ sung |

Java 27 tiếp tục Lazy Constants ở lần preview thứ ba theo **JEP 531**. Trong release này, `Set.ofLazy` mở rộng mô hình lazy collection sang Set. Vì vậy, ví dụ sử dụng cả ba factory trong bài phải biên dịch và chạy bằng JDK 27.

Không dùng mã gọi `Set.ofLazy` với JDK 26. Cũng cần lưu ý thay đổi xử lý lỗi: Java 26 chuyển tiếp exception từ computing function cho caller và không ghi nhận giá trị; Java 27 đưa phần tử hoặc trạng thái thành viên bị lỗi vào trạng thái lỗi cố định. Khác biệt này được giải thích ở phần 8.

## 2. Phân biệt unmodifiable, immutable và unmodifiable view

Ba khái niệm thường bị nhầm lẫn:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Modifiable | Có thể thay đổi cấu trúc bằng các phương thức sửa đổi | `ArrayList`, `HashMap`, `HashSet` |
| Unmodifiable | Các phương thức sửa đổi bị chặn; thao tác đó ném `UnsupportedOperationException` | `List.of`, `List.copyOf`, các lazy collection |
| Immutable | Trạng thái quan sát được không thể thay đổi sau khi tạo | Tập hợp unmodifiable chứa toàn phần tử immutable, hoặc một cấu trúc bất biến được thiết kế đúng |

Một tập hợp unmodifiable không nhất thiết immutable. Ví dụ, List không cho gọi `set`, nhưng nếu phần tử là một đối tượng có phương thức `rename`, người gọi vẫn có thể đổi tên đối tượng đó. Khi đọc lại List, nội dung phần tử đã thay đổi.

Cũng cần phân biệt **unmodifiable view** với một tập hợp unmodifiable được tạo từ factory. `Collections.unmodifiableList(backingList)` là view của danh sách gốc. Nếu mã khác còn giữ `backingList` và sửa nó, các thay đổi sẽ xuất hiện qua view. Trong khi đó, `List.copyOf(source)` tạo một tập hợp unmodifiable độc lập với các thay đổi cấu trúc về sau của nguồn; tuy nhiên, đây vẫn là bản sao nông, không sao chép sâu từng đối tượng phần tử.

Các lazy factory `List.ofLazy`, `Map.ofLazy` và `Set.ofLazy` trả về các tập hợp unmodifiable. Chúng quản lý việc tính giá trị hoặc trạng thái thành viên theo nhu cầu. Chúng không tự biến các đối tượng được trả về thành immutable.

## 3. Ba dạng lazy collection trong Java 27

| Factory | Cách xác định phần tử | Thời điểm tính |
|---|---|---|
| `List.ofLazy(size, function)` | Kích thước và vị trí phần tử được xác định trước | Khi truy cập chỉ số lần đầu bằng `get(index)` |
| `Map.ofLazy(keys, function)` | Tập khóa được xác định trước | Khi truy cập giá trị lần đầu bằng `get(key)` hoặc view cần giá trị |
| `Set.ofLazy(candidates, predicate)` | Tập ứng viên được xác định trước; predicate quyết định ứng viên có thuộc Set hay không | Khi cần kiểm tra thành viên, chẳng hạn `contains(candidate)` |

Cả ba factory đều tạo cấu trúc unmodifiable. Computing function được bảo đảm chạy tối đa một lần thành công cho mỗi vị trí, khóa hoặc ứng viên tương ứng trong môi trường nhiều luồng. Nếu nhiều luồng cùng truy cập một phần tử đang được tính, các luồng cạnh tranh chờ cho đến khi việc tính phần tử đó hoàn tất hoặc thất bại.

### Lazy List

`List.ofLazy` tạo một List có kích thước cố định. Giá trị ở từng chỉ số được tính riêng khi truy cập. Phần tử ở chỉ số 0 có thể đã được khởi tạo trong khi các chỉ số khác vẫn chưa được tính.

    List<String> names = List.ofLazy(
            4,
            index -> "user-" + index
    );

    System.out.println(names.size()); // 4
    System.out.println(names.get(2)); // Tính phần tử chỉ số 2
    System.out.println(names.get(2)); // Dùng lại kết quả đã tính

Các thao tác thay đổi cấu trúc như `add`, `remove`, `clear` hoặc thay thế phần tử bằng `set` không được hỗ trợ. `subList()` và `reversed()` tiếp tục là view có các phần tử được tính trễ.

### Lazy Map

`Map.ofLazy` nhận một tập khóa đã biết và một Function tính giá trị theo khóa. Tập khóa không thay đổi sau khi tạo Map; mỗi giá trị được tính khi lần đầu truy cập khóa đó.

    Set<String> currencies = Set.of("USD", "EUR", "JPY");

    Map<String, String> currencyNames = Map.ofLazy(
            currencies,
            code -> switch (code) {
                case "USD" -> "US Dollar";
                case "EUR" -> "Euro";
                case "JPY" -> "Japanese Yen";
                default -> throw new IllegalArgumentException(code);
            }
    );

    System.out.println(currencyNames.get("EUR"));

Map không cho thêm, xóa hoặc cập nhật mapping; khóa và value không được là `null`. Các view `values()` và `entrySet()` cũng truy xuất giá trị theo cơ chế lazy. Việc duyệt toàn bộ Map hoặc gọi các phương thức như `equals`, `hashCode`, `toString` có thể làm khởi tạo nhiều hoặc toàn bộ giá trị.

Tập khóa đầu vào phải dùng `equals()` làm quan hệ tương đương, hoặc comparator phải nhất quán với `equals()`; nếu không, hành vi không được xác định. Nếu tập khóa ban đầu bị sửa sau khi tạo Map, Map đã tạo không phản ánh thay đổi đó.

### Lazy Set

`Set.ofLazy` được bổ sung trong Java 27. Thay vì tạo giá trị cho mỗi phần tử, factory nhận một tập ứng viên và Predicate xác định ứng viên nào thực sự là thành viên.

    enum Feature {
        AUDIT, EXPORT, BETA
    }

    static boolean isEnabled(Feature feature) {
        return switch (feature) {
            case AUDIT, EXPORT -> true;
            case BETA -> false;
        };
    }

    static final Set<Feature> ENABLED_FEATURES =
            Set.ofLazy(
                    EnumSet.allOf(Feature.class),
                    LazyFeatureDemo::isEnabled
            );

    // Predicate chỉ được gọi khi cần xác định membership.
    boolean auditEnabled = ENABLED_FEATURES.contains(Feature.AUDIT);

Kết quả membership của mỗi ứng viên được tính trễ và lưu lại, dù ứng viên thuộc Set hay không thuộc Set. Set kết quả không cho thêm hoặc xóa phần tử. Thay đổi tập ứng viên đầu vào sau khi tạo Set không làm thay đổi Set kết quả.

Tập ứng viên cũng phải có quy tắc tương đương nhất quán: dùng `equals()` hoặc comparator nhất quán với `equals()`. Không dùng các đối tượng làm ứng viên nếu các field tham gia `equals`/`hashCode` có thể thay đổi trong lúc chúng là phần tử của Set.

## 4. Unmodifiable không khóa được trạng thái bên trong phần tử

Ví dụ sau cho thấy một Lazy List không cho thay thế phần tử, nhưng đối tượng phần tử vẫn có thể thay đổi:

    import java.util.List;

    public class MutableElementDemo {

        static final class Profile {
            private String displayName;

            Profile(String displayName) {
                this.displayName = displayName;
            }

            void rename(String newName) {
                this.displayName = newName;
            }

            String displayName() {
                return displayName;
            }
        }

        public static void main(String[] args) {
            List<Profile> profiles = List.ofLazy(
                    2,
                    index -> new Profile("user-" + index)
            );

            Profile first = profiles.get(0);
            first.rename("administrator");

            System.out.println(profiles.get(0).displayName());

            try {
                profiles.set(0, new Profile("replacement"));
            } catch (UnsupportedOperationException expected) {
                System.out.println("Không thể thay thế phần tử trong List");
            }
        }
    }

Biên dịch và chạy trên JDK 27:

    javac --enable-preview --release 27 -encoding UTF-8 -d out src/MutableElementDemo.java
    java --enable-preview -cp out MutableElementDemo

Kết quả:

    administrator
    Không thể thay thế phần tử trong List

Lệnh `rename` thay đổi object `Profile` mà List đang giữ. Nó không thay đổi vị trí hoặc tham chiếu được lưu trong List. Ngược lại, `set` cố thay tham chiếu ở vị trí 0 nên bị từ chối.

Điều này cũng áp dụng cho Map và Set. Map không cho `put` hoặc `replace` một value, nhưng object value có thể có phương thức thay đổi state. Set không cho `add` hoặc `remove`, nhưng object được lưu có thể vẫn mutable. Vì vậy, không thể kết luận dữ liệu an toàn để chia sẻ chỉ từ việc factory trả về một tập hợp unmodifiable.

## 5. Làm cho phần tử immutable

Muốn tập hợp unmodifiable trở thành effectively immutable, cần thiết kế phần tử sao cho trạng thái quan sát được của chúng không thể đổi sau khi tạo.

Các lựa chọn phù hợp:

- Dùng kiểu giá trị immutable như `String`, wrapper primitive, enum hoặc record chỉ chứa các thành phần immutable.
- Dùng field `private final`, không cung cấp setter hoặc phương thức làm thay đổi trạng thái.
- Với collection lồng nhau, tạo bản sao unmodifiable trong constructor hoặc factory.
- Không để lộ mảng, collection hoặc object mutable nội bộ qua accessor.
- Với khóa Map hoặc ứng viên Set, giữ ổn định `equals()`, `hashCode()` và quy tắc so sánh trong suốt vòng đời sử dụng.

Ví dụ dùng record và sao chép danh sách vai trò:

    import java.util.List;

    record UserProfile(String name, List<String> roles) {
        UserProfile {
            roles = List.copyOf(roles);
        }
    }

    static final List<UserProfile> USERS = List.ofLazy(
            2,
            index -> index == 0
                    ? new UserProfile("An", List.of("ADMIN", "AUDIT"))
                    : new UserProfile("Binh", List.of("READER"))
    );

Record tạo các thành phần final. Constructor gán một List unmodifiable cho `roles`, còn các phần tử String cũng immutable. Trong ví dụ này, cấu trúc và dữ liệu quan sát được của từng UserProfile không thay đổi sau khi khởi tạo.

Cần nhớ rằng `List.copyOf` chỉ sao chép cấu trúc collection, không tự sao chép sâu object bên trong. Nếu danh sách đầu vào chứa các object mutable, những object đó vẫn có thể bị thay đổi qua tham chiếu khác. Khi cần bất biến sâu, hãy chuyển từng phần tử sang dạng immutable hoặc tạo defensive copy theo mô hình dữ liệu cụ thể.

## 6. Bảo vệ khóa Map và ứng viên Set

Map và Set phụ thuộc vào `equals()` và `hashCode()` để nhận diện khóa hoặc phần tử. Nếu một object thay đổi field tham gia hai phương thức này sau khi được dùng làm khóa Map hoặc phần tử Set, việc tra cứu có thể không còn đúng như mong đợi.

Ví dụ không an toàn:

    final class MutableKey {
        private String code;

        MutableKey(String code) {
            this.code = code;
        }

        void changeCode(String code) {
            this.code = code;
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof MutableKey key
                    && code.equals(key.code);
        }

        @Override
        public int hashCode() {
            return code.hashCode();
        }
    }

Nếu dùng MutableKey làm khóa cho `Map.ofLazy` rồi gọi `changeCode`, kết quả `hashCode` có thể khác giá trị tại thời điểm tạo Map. Tương tự, thay đổi field tham gia so sánh của ứng viên Set có thể phá vỡ giả định membership và tra cứu.

Nên dùng enum, String hoặc record có các thành phần immutable làm khóa/ứng viên:

    record RegionCode(String value) {
    }

    Set<RegionCode> candidates = Set.of(
            new RegionCode("APAC"),
            new RegionCode("EMEA")
    );

    Map<RegionCode, String> regionNames = Map.ofLazy(
            candidates,
            key -> key.value().equals("APAC")
                    ? "Asia Pacific"
                    : "Europe, Middle East and Africa"
    );

Record không tự bảo đảm immutable sâu nếu component là object mutable. Trong ví dụ, component là String nên `RegionCode` có giá trị ổn định.

## 7. Tập hợp unmodifiable có thể thay đổi nội dung quan sát được khi nào?

Một tập hợp unmodifiable có thể thay đổi nội dung quan sát được trong một số trường hợp:

1. **Phần tử mutable:** object đã được trả về có thể thay đổi field hoặc dữ liệu bên trong.
2. **Unmodifiable view:** collection gốc còn có thể được sửa thông qua một tham chiếu khác; view phản ánh thay đổi đó.
3. **Lazy computation:** trước khi truy cập, phần tử hoặc trạng thái membership chưa được tính. Lần đọc đầu tiên làm xuất hiện giá trị đã tính. Đây là quá trình hoàn thiện giá trị đã định nghĩa bởi computing function, không phải thao tác sửa cấu trúc collection.
4. **Hàm tính dựa trên dữ liệu ngoài:** giá trị được tính theo trạng thái bên ngoài tại lần truy cập đầu. Sau khi được tính, kết quả được lưu; thay đổi cấu hình ngoài sau đó không tự tính lại phần tử đã có.

Với Lazy List, `size()` đã được xác định khi tạo, dù các giá trị chưa được tính. Với Lazy Map, tập khóa đã được xác định khi tạo, dù các value chưa có. Với Lazy Set, tập ứng viên đã được xác định, còn việc ứng viên có thuộc Set hay không được xác định theo nhu cầu.

Không dùng lazy collection nếu yêu cầu dữ liệu phải tự cập nhật theo cấu hình hoặc nguồn dữ liệu thay đổi liên tục. Khi cần refresh, eviction hoặc cập nhật, hãy dùng cấu trúc có thể thay đổi với cơ chế đồng bộ và chính sách vòng đời rõ ràng.

## 8. Xử lý lỗi và khác biệt giữa JDK 26 với JDK 27

Trong JDK 27, nếu computing function của List hoặc Map ném unchecked exception, phần tử tương ứng chuyển sang trạng thái lỗi. Lần truy cập đầu tiên ném `NoSuchElementException` có exception gốc làm cause. Những lần truy cập tiếp theo cũng ném `NoSuchElementException`, không gọi lại computing function và không có cause gốc trong exception mới.

Nếu List computing function hoặc Map computing function trả về `null`, lần truy cập ném `NoSuchElementException` có `NullPointerException` làm cause. Lazy List không chứa null; Lazy Map không chứa null value. Muốn biểu diễn một kết quả có thể vắng mặt, dùng `Optional` làm phần tử hoặc value.

Với Set, nếu Predicate ném unchecked exception khi xác định membership của một ứng viên, trạng thái membership đó chuyển sang error state. Lần `contains` đầu tiên ném `NoSuchElementException` có cause; lần gọi tiếp theo cho cùng ứng viên tiếp tục ném `NoSuchElementException` mà không gọi lại Predicate. Set membership là boolean nên không có trường hợp Predicate trả về null.

| Tình huống | JDK 26 | JDK 27 |
|---|---|---|
| List/Map computing function ném exception | Chuyển tiếp exception cho caller; chưa ghi giá trị, lần truy cập sau có thể thử lại | Phần tử chuyển sang error state; lần đầu ném NoSuchElementException có cause, lần sau không tính lại |
| List/Map computing function trả null | Ném NullPointerException | Ném NoSuchElementException có NullPointerException làm cause |
| Set.ofLazy | Chưa có factory | Có; lỗi Predicate chuyển membership sang error state |
| Lazy collection vẫn preview | Có | Có |

Đệ quy computing function cho cùng chỉ số hoặc khóa gây lỗi. Trong JDK 27, lỗi đệ quy được thể hiện qua `NoSuchElementException` có `IllegalStateException` làm cause. Với Set, quy tắc tương tự áp dụng khi Predicate đệ quy kiểm tra chính ứng viên đang được tính.

Không giả định lazy collection tự retry khi lỗi tạm thời trong JDK 27. Nếu tác vụ có thể thất bại tạm thời và cần retry, hãy đặt chính sách retry bên trong tầng ứng dụng hoặc dùng cơ chế có thể cập nhật phù hợp thay vì trông đợi factory lazy tự chạy lại.

## 9. Các thao tác có thể kích hoạt tính toán ngoài dự kiến

Lazy collection không có nghĩa mọi thao tác đều chỉ đọc metadata mà không tính phần tử. Một số thao tác cần biết nội dung thực tế nên có thể kích hoạt computing function:

- `List.get(index)` tính phần tử tại chỉ số đó.
- `Map.get(key)` tính value tương ứng với khóa hợp lệ.
- `Set.contains(candidate)` tính trạng thái membership của ứng viên.
- Duyệt toàn bộ List, Map hoặc Set có thể làm tính nhiều hoặc toàn bộ phần tử.
- `equals()`, `hashCode()`, `toString()` có thể làm khởi tạo một hoặc nhiều phần tử.

Vì vậy, tránh ghi log trực tiếp một lazy collection lớn nếu không muốn khởi tạo nhiều phần tử ngoài dự kiến. Đặc biệt, gọi `toString()` để debug có thể kích hoạt các phép tính vốn chưa cần thiết cho luồng nghiệp vụ.

Lazy List, Lazy Map và Lazy Set không Serializable theo hợp đồng API hiện tại. Computing function được giữ tham chiếu mạnh trong khi còn phần tử chưa tính; closure của function có thể giữ theo các object khác. Tránh capture một object đồ sộ hoặc tài nguyên có vòng đời ngắn nếu không cần thiết.

## 10. Thread safety không đồng nghĩa với phần tử immutable

Lazy collection bảo đảm việc tính mỗi phần tử hoặc membership status tối đa một lần trong môi trường nhiều luồng. Nếu hai luồng cùng truy cập một index, key hoặc candidate đang được tính, một luồng thực hiện computing function và luồng cạnh tranh chờ kết quả.

Bảo đảm này bảo vệ quá trình khởi tạo lazy. Nó không tự đồng bộ những lần sửa state của object sau khi object đã được trả về. Ví dụ, nếu một List lazy chứa `ArrayList` và nhiều luồng cùng sửa ArrayList đó, ứng dụng vẫn phải đồng bộ riêng hoặc thay bằng collection đồng thời phù hợp.

Mô hình an toàn hơn là để computing function tạo một object đã hoàn chỉnh, dùng các field final, record, collection lồng nhau unmodifiable và không thay đổi state sau khi trả về. Khi dữ liệu cần cập nhật, hãy tách phần dữ liệu mutable ra khỏi cấu trúc lazy và áp dụng cơ chế concurrency phù hợp.

## 11. Biên dịch và chạy preview bằng JDK 27

Các factory `List.ofLazy`, `Map.ofLazy` và `Set.ofLazy` là preview API. Dùng JDK 27 cho cả compiler và runtime, đồng thời bật preview ở hai bước.

Kiểm tra phiên bản:

    java --version
    javac --version

Biên dịch:

    javac --enable-preview --release 27 -encoding UTF-8 -d out src/LazyCollectionDemo.java

Chạy:

    java --enable-preview -cp out LazyCollectionDemo

Các API nằm trong module `java.base`, vì vậy không cần `--add-modules`. Nếu dùng Gradle hoặc IDE, cấu hình JDK 27 cho compiler toolchain, test JVM và application runner; truyền `--enable-preview` vào cả compiler và các JVM chạy mã preview.

JDK 26 chỉ có List.ofLazy và Map.ofLazy trong preview; không biên dịch ví dụ Set.ofLazy bằng JDK 26. Khi chuyển release, cần biên dịch lại và kiểm tra lại semantics xử lý lỗi thay vì dùng class file preview của release trước.

## 12. Chọn cách tạo collection theo yêu cầu dữ liệu

| Nhu cầu | Lựa chọn |
|---|---|
| Tập hợp nhỏ, giá trị đã biết và bất biến | `List.of`, `Set.of`, `Map.of` |
| Tạo snapshot unmodifiable từ collection hiện có | `List.copyOf`, `Set.copyOf`, `Map.copyOf` |
| Cung cấp read-only view của collection nội bộ | `Collections.unmodifiableList/Set/Map`, đồng thời kiểm soát tham chiếu backing collection |
| Danh sách kích thước cố định, tính phần tử khi cần | `List.ofLazy` |
| Tập khóa cố định, tính value khi cần | `Map.ofLazy` |
| Tập ứng viên cố định, tính membership khi cần | `Set.ofLazy` |
| Dữ liệu cần thêm/xóa/cập nhật thường xuyên | Collection modifiable hoặc cấu trúc đồng thời thích hợp |

Đừng dùng Lazy Collections chỉ vì muốn một collection không sửa đổi được. Nếu mọi phần tử đã biết và có sẵn, `List.of`, `Map.of`, `Set.of` hoặc `copyOf` đơn giản hơn và không yêu cầu bật preview. Chọn lazy factory khi chi phí tạo phần tử lớn, chỉ một phần phần tử được dùng, hoặc cần khởi tạo từng phần tử theo nhu cầu.

## 13. Checklist thiết kế bất biến

1. Xác định collection chỉ cần unmodifiable hay cần effectively immutable.
2. Kiểm tra từng phần tử, value và key có mutable hay không.
3. Với Map/Set, bảo đảm `equals()`, `hashCode()` và comparator không thay đổi theo thời gian.
4. Dùng record, enum, String hoặc kiểu immutable cho phần tử nếu có thể.
5. Với collection lồng nhau, tạo defensive copy và kiểm tra cả các phần tử bên trong.
6. Không cho object mutable thoát khỏi computing function trước khi khởi tạo hoàn chỉnh.
7. Không giả định List.ofLazy, Map.ofLazy và Set.ofLazy tự deep-copy hoặc freeze object được trả về.
8. Kiểm tra các thao tác có thể kích hoạt tính toán như iteration, `toString()`, `equals()` và `hashCode()`.
9. Xác định cách xử lý lỗi: JDK 27 chuyển phần tử lỗi sang error state và không tự retry.
10. Bật preview ở compiler và runtime cùng JDK 27; xác nhận release trước khi nâng cấp.

## Tài liệu chính thức

- [Java SE 27 API — Collection](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Collection.html): phân biệt unmodifiable, immutable và unmodifiable view.
- [Java SE 27 API — List.ofLazy](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/List.html): hợp đồng lazy list, unmodifiable, tính một lần, error state, view và các thao tác có thể kích hoạt khởi tạo.
- [Java SE 27 API — Map.ofLazy](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Map.html): tập khóa cố định, lazy values, quy tắc khóa và error state.
- [Java SE 27 API — Set.ofLazy](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Set.html): lazy membership theo tập ứng viên và Predicate.
- [Oracle — Lazy Constants, Java SE 27 Core Libraries](https://docs.oracle.com/en/java/javase/27/core/lazy-constants.html): ví dụ Lazy List, Lazy Map, Lazy Set, thread safety và constant folding.
- [Java SE 26 API — List.ofLazy](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/List.html): đối chiếu hành vi lỗi của Lazy List trong preview Java 26.
- [Java SE 26 API — Map.ofLazy](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Map.html): đối chiếu Lazy Map và việc chuyển tiếp exception trong preview Java 26.
- [Oracle — JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html): xác nhận Lazy Constants là preview lần thứ ba theo JEP 531.

Tại ngày 27-11-2026, Lazy Collections trong JDK 27 vẫn là preview API. Cấu trúc unmodifiable được bảo đảm bởi factory, còn tính immutable của phần tử phải được thiết kế và kiểm chứng riêng. Chỉ dùng cho thử nghiệm có kiểm soát cho đến khi API trở thành final và dự án xác nhận lại tính tương thích.
