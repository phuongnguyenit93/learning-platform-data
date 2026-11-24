# Theo dõi luồng gọi từ client đến ConcreteFactory và ConcreteProduct

## 1. Mục tiêu của việc theo dõi luồng khởi tạo

Trong mẫu thiết kế **Abstract Factory**, client làm việc với một **abstract factory** để lấy các sản phẩm thuộc cùng một họ. Client không cần tự chọn lớp sản phẩm cụ thể cho từng lần tạo.

Điều này tạo ra hai bước đa hình liên tiếp:

1. Client gọi phương thức của **abstract factory**; tại thời điểm chạy, lời gọi được chuyển đến **concrete factory** đã được cấu hình.
2. Client nhận sản phẩm qua **product interface**; khi gọi phương thức của sản phẩm, hành vi thực thi thuộc về **concrete product** được factory trả về.

Ví dụ một ứng dụng hỗ trợ giao diện **Light** và **Dark**. Mỗi họ có `Button` và `Checkbox`. Client `SettingsScreen` cần cả hai loại sản phẩm để dựng một màn hình cài đặt.

Câu hỏi trọng tâm của bài học thuộc chương **Luồng khởi tạo** là:

> Từ lúc ứng dụng quyết định dùng Light hoặc Dark, những đối tượng nào nhận lời gọi, đối tượng nào thực sự được tạo ra và client sử dụng sản phẩm ấy như thế nào?

Sau bài này, bạn sẽ có thể đọc một sequence diagram, lần theo code Java, đặt breakpoint đúng vị trí và giải thích vì sao thay concrete factory có thể thay cả họ sản phẩm mà không phải sửa logic của client.

## 2. Nhận diện các vai trò trước khi đọc trace

| Vai trò | Thành phần trong ví dụ | Điều client biết |
| --- | --- | --- |
| **Client** | `SettingsScreen` | Phụ thuộc `UiFactory`, `Button`, `Checkbox` |
| **AbstractFactory** | `UiFactory` | Công bố `createButton()` và `createCheckbox()` |
| **ConcreteFactory** | `LightUiFactory` hoặc `DarkUiFactory` | Chọn lớp sản phẩm thuộc họ tương ứng |
| **AbstractProduct** | `Button`, `Checkbox` | Công bố thao tác `render()` |
| **ConcreteProduct** | `LightButton`, `LightCheckbox`, `DarkButton`, `DarkCheckbox` | Cung cấp hành vi render cụ thể |
| **Composition root** | `main()` | Đọc cấu hình và tiêm concrete factory vào client |

**Composition root** là nơi lắp ráp các dependency của ứng dụng, thường tại bootstrap hoặc điểm cấu hình dependency injection (DI). Nó có thể biết các concrete class. Client nghiệp vụ vẫn chỉ làm việc với các abstraction.

Sơ đồ các quan hệ về kiểu:

~~~mermaid
classDiagram
    class UiFactory {
        <<interface>>
        +createButton() Button
        +createCheckbox() Checkbox
    }
    class Button {
        <<interface>>
        +render() void
    }
    class Checkbox {
        <<interface>>
        +render() void
    }
    class LightUiFactory
    class DarkUiFactory
    class LightButton
    class DarkButton
    class LightCheckbox
    class DarkCheckbox
    class SettingsScreen

    UiFactory <|.. LightUiFactory
    UiFactory <|.. DarkUiFactory
    Button <|.. LightButton
    Button <|.. DarkButton
    Checkbox <|.. LightCheckbox
    Checkbox <|.. DarkCheckbox
    SettingsScreen --> UiFactory : su dung
    SettingsScreen --> Button : nhan qua interface
    SettingsScreen --> Checkbox : nhan qua interface
    LightUiFactory ..> LightButton : tao
    LightUiFactory ..> LightCheckbox : tao
    DarkUiFactory ..> DarkButton : tao
    DarkUiFactory ..> DarkCheckbox : tao
~~~

Đường biểu diễn interface và dependency cho biết **ai có thể gọi ai**. Nó chưa thể hiện **thứ tự lời gọi khi chạy**. Để xem thứ tự, cần sequence diagram và bản ghi trace.

## 3. Luồng chạy chuẩn: chọn factory, tạo product, sử dụng product

Khi cấu hình là `light`, chuỗi sự kiện có thể được tách thành sáu bước.

1. **Chọn họ:** `main()` tạo `LightUiFactory` và lưu tham chiếu đó dưới kiểu `UiFactory`.
2. **Tiêm factory:** `main()` truyền factory vào constructor của `SettingsScreen`. Client lưu tham chiếu; chưa cần tạo Button hoặc Checkbox ngay.
3. **Yêu cầu Button:** `SettingsScreen.show()` gọi `factory.createButton()`. Vì đối tượng runtime là `LightUiFactory`, Java thực thi phương thức `LightUiFactory.createButton()`.
4. **Tạo và trả Button:** Concrete factory tạo `LightButton`, trả về cho client dưới kiểu `Button`.
5. **Yêu cầu Checkbox:** Tương tự, `createCheckbox()` chạy trong `LightUiFactory`, tạo `LightCheckbox` và trả về dưới kiểu `Checkbox`.
6. **Sử dụng sản phẩm:** Client gọi `button.render()` và `checkbox.render()`. Java chuyển các lời gọi này đến `LightButton.render()` và `LightCheckbox.render()`.

~~~mermaid
sequenceDiagram
    autonumber
    participant Bootstrap as main / bootstrap
    participant Client as SettingsScreen
    participant Factory as LightUiFactory
    participant Button as LightButton
    participant Checkbox as LightCheckbox

    Bootstrap->>Factory: new LightUiFactory()
    Bootstrap->>Client: new SettingsScreen(factory: UiFactory)
    Client->>Factory: createButton()
    activate Factory
    Factory->>Button: new LightButton()
    Button-->>Factory: instance
    Factory-->>Client: Button
    deactivate Factory
    Client->>Factory: createCheckbox()
    activate Factory
    Factory->>Checkbox: new LightCheckbox()
    Checkbox-->>Factory: instance
    Factory-->>Client: Checkbox
    deactivate Factory
    Client->>Button: render()
    Button-->>Client: hoàn tất render
    Client->>Checkbox: render()
    Checkbox-->>Client: hoàn tất render
~~~

Chú ý sự khác nhau giữa **kiểu khai báo** và **kiểu thật khi chạy**:

| Biểu thức tại client | Kiểu khai báo | Đối tượng thực tế khi chọn Light | Phương thức được thực thi |
| --- | --- | --- | --- |
| `factory` | `UiFactory` | `LightUiFactory` | `LightUiFactory.createButton/createCheckbox` |
| `button` | `Button` | `LightButton` | `LightButton.render` |
| `checkbox` | `Checkbox` | `LightCheckbox` | `LightCheckbox.render` |

**Sản phẩm không bị biến thành interface.** Biến `button` chỉ có **kiểu tham chiếu** là `Button`; đối tượng trong bộ nhớ vẫn là `LightButton`. Đây là cách đa hình giúp client giữ nguyên code.

## 4. Ví dụ Java chạy độc lập để quan sát các lời gọi

Ví dụ sử dụng Java 17 trở lên, đặt toàn bộ code dưới đây trong một file `AbstractFactoryTraceDemo.java`. Các lệnh ghi log được đặt ngay tại điểm client yêu cầu sản phẩm và concrete factory tạo sản phẩm để dễ đối chiếu với sequence diagram.

~~~java
import java.util.Locale;
import java.util.Objects;

public final class AbstractFactoryTraceDemo {

    // Abstract products
    interface Button {
        void render();
    }

    interface Checkbox {
        void render();
    }

    // Abstract factory
    interface UiFactory {
        Button createButton();
        Checkbox createCheckbox();
    }

    // Light product family
    static final class LightButton implements Button {
        @Override
        public void render() {
            System.out.println("LightButton: render()");
        }
    }

    static final class LightCheckbox implements Checkbox {
        @Override
        public void render() {
            System.out.println("LightCheckbox: render()");
        }
    }

    // Dark product family
    static final class DarkButton implements Button {
        @Override
        public void render() {
            System.out.println("DarkButton: render()");
        }
    }

    static final class DarkCheckbox implements Checkbox {
        @Override
        public void render() {
            System.out.println("DarkCheckbox: render()");
        }
    }

    // Concrete factories
    static final class LightUiFactory implements UiFactory {
        @Override
        public Button createButton() {
            System.out.println("LightUiFactory: new LightButton");
            return new LightButton();
        }

        @Override
        public Checkbox createCheckbox() {
            System.out.println("LightUiFactory: new LightCheckbox");
            return new LightCheckbox();
        }
    }

    static final class DarkUiFactory implements UiFactory {
        @Override
        public Button createButton() {
            System.out.println("DarkUiFactory: new DarkButton");
            return new DarkButton();
        }

        @Override
        public Checkbox createCheckbox() {
            System.out.println("DarkUiFactory: new DarkCheckbox");
            return new DarkCheckbox();
        }
    }

    // Client: chỉ phụ thuộc các interface
    static final class SettingsScreen {
        private final UiFactory factory;

        SettingsScreen(UiFactory factory) {
            this.factory = Objects.requireNonNull(factory);
            System.out.println("Client: receives UiFactory");
        }

        void show() {
            System.out.println("Client: createButton()");
            Button button = factory.createButton();

            System.out.println("Client: createCheckbox()");
            Checkbox checkbox = factory.createCheckbox();

            System.out.println("Client: Button.render()");
            button.render();

            System.out.println("Client: Checkbox.render()");
            checkbox.render();
        }
    }

    // Composition root: được phép chọn implementation cụ thể
    public static void main(String[] args) {
        String mode = args.length == 0
            ? "light"
            : args[0].toLowerCase(Locale.ROOT);

        UiFactory factory = switch (mode) {
            case "light" -> new LightUiFactory();
            case "dark" -> new DarkUiFactory();
            default -> throw new IllegalArgumentException(
                "Unsupported UI family: " + mode
            );
        };

        System.out.println(
            "Bootstrap: selected " + factory.getClass().getSimpleName()
        );

        new SettingsScreen(factory).show();
    }
}
~~~

Biên dịch và chạy trên máy có JDK 17+:

~~~bash
javac AbstractFactoryTraceDemo.java
java AbstractFactoryTraceDemo light
~~~

Kết quả dự kiến khi dùng Light:

~~~text
Bootstrap: selected LightUiFactory
Client: receives UiFactory
Client: createButton()
LightUiFactory: new LightButton
Client: createCheckbox()
LightUiFactory: new LightCheckbox
Client: Button.render()
LightButton: render()
Client: Checkbox.render()
LightCheckbox: render()
~~~

Kết quả này là **output dự kiến từ ví dụ**, chưa phải nhật ký thực thi được thu thập từ dự án của người học.

### Giải mã từng dòng log

| Log | Ai chủ động? | Ý nghĩa khi lần theo call stack |
| --- | --- | --- |
| `Bootstrap: selected LightUiFactory` | `main()` | Xác định concrete factory trước khi client chạy |
| `Client: receives UiFactory` | Constructor của client | Client nhận dependency, không trực tiếp tạo concrete product |
| `Client: createButton()` | Client | Chuẩn bị gọi qua `UiFactory` |
| `LightUiFactory: new LightButton` | Concrete factory | Dynamic dispatch chọn đúng factory, rồi factory cấp phát product |
| `Client: createCheckbox()` | Client | Tiếp tục yêu cầu loại sản phẩm thứ hai |
| `LightUiFactory: new LightCheckbox` | Concrete factory | Tạo product cùng họ với Button |
| `Client: Button.render()` | Client | Gọi phương thức qua `Button` |
| `LightButton: render()` | Concrete product | Hành vi thật được chạy |
| `Client: Checkbox.render()` | Client | Gọi phương thức qua `Checkbox` |
| `LightCheckbox: render()` | Concrete product | Hành vi thật của Checkbox được chạy |

Một điểm thường gây nhầm: dòng `Client: Button.render()` không phải lời gọi đến factory. Sau khi factory trả sản phẩm, client làm việc trực tiếp với **product interface**. Factory chỉ tham gia lần nữa nếu client cần yêu cầu thêm sản phẩm hoặc API thiết kế một bước tạo khác.

## 5. Chạy cùng client với họ Dark

Thực hiện:

~~~bash
java AbstractFactoryTraceDemo dark
~~~

Output dự kiến:

~~~text
Bootstrap: selected DarkUiFactory
Client: receives UiFactory
Client: createButton()
DarkUiFactory: new DarkButton
Client: createCheckbox()
DarkUiFactory: new DarkCheckbox
Client: Button.render()
DarkButton: render()
Client: Checkbox.render()
DarkCheckbox: render()
~~~

So sánh hai lần chạy:

| Vị trí trong luồng | Khi chọn Light | Khi chọn Dark |
| --- | --- | --- |
| Composition root | Tạo `LightUiFactory` | Tạo `DarkUiFactory` |
| `factory.createButton()` | `LightUiFactory.createButton()` | `DarkUiFactory.createButton()` |
| Product trả về | `LightButton` | `DarkButton` |
| `factory.createCheckbox()` | `LightUiFactory.createCheckbox()` | `DarkUiFactory.createCheckbox()` |
| Product trả về | `LightCheckbox` | `DarkCheckbox` |
| `button.render()` | `LightButton.render()` | `DarkButton.render()` |
| `checkbox.render()` | `LightCheckbox.render()` | `DarkCheckbox.render()` |

**Không cần sửa `SettingsScreen`.** Dòng `new SettingsScreen(factory).show()` và toàn bộ thân `show()` giữ nguyên. Chỉ có đối tượng factory được lắp vào ở composition root là khác.

Đây là lợi ích then chốt của Abstract Factory: thay một dependency có thể thay đồng bộ nhiều loại sản phẩm cùng họ.

## 6. Xác định chính xác điểm xảy ra dynamic dispatch

Đọc đoạn code:

~~~java
UiFactory factory = new DarkUiFactory();
Button button = factory.createButton();
button.render();
~~~

Ở dòng đầu, biến được khai báo với kiểu `UiFactory` nhưng tham chiếu đến một `DarkUiFactory`. Ở dòng thứ hai, `createButton()` là phương thức instance được override; Java chọn implementation dựa trên **đối tượng runtime** `DarkUiFactory`. Phương thức này thực thi `new DarkButton()` và trả tham chiếu kiểu `Button`.

Dòng thứ ba tiếp tục dynamic dispatch trên **đối tượng runtime khác**: `DarkButton`. Java chạy `DarkButton.render()`.

Có thể hình dung thành hai nút quyết định:

~~~mermaid
flowchart TD
    A["Client gọi factory.createButton()"] --> B{"Runtime factory là gì?"}
    B -->|"LightUiFactory"| C["Tạo LightButton"]
    B -->|"DarkUiFactory"| D["Tạo DarkButton"]
    C --> E["Client nhận Button"]
    D --> E
    E --> F["Client gọi button.render()"]
    F --> G{"Runtime product là gì?"}
    G -->|"LightButton"| H["LightButton.render()"]
    G -->|"DarkButton"| I["DarkButton.render()"]
~~~

Đây là **hai điểm đa hình riêng biệt**, không phải factory tự chuyển tiếp mọi lời gọi thao tác sản phẩm. Nếu đang debug, bạn có thể thấy stack khi tạo product đi qua concrete factory; nhưng sau khi trả về, stack khi render thường đi trực tiếp từ client đến concrete product.

Lưu ý rằng `new DarkUiFactory()` tự nó không phải dynamic dispatch: đó là biểu thức khởi tạo cụ thể do composition root lựa chọn. Sự đa hình nằm ở các lời gọi phương thức trên biến kiểu interface.

## 7. Khi nào client gọi factory? Không có thứ tự cố định do pattern áp đặt

Abstract Factory chỉ mô tả **họ sản phẩm và giao diện khởi tạo**. Pattern không yêu cầu mọi client luôn gọi `createButton()` trước `createCheckbox()`, cũng không buộc sản phẩm được tạo sớm hoặc mới hoàn toàn trong mỗi lời gọi.

Có ba cách tổ chức thường gặp:

| Thời điểm tạo | Luồng gọi | Khi nào phù hợp |
| --- | --- | --- |
| **Eager** | Constructor client gọi các phương thức factory ngay khi client được dựng | Bộ sản phẩm nhỏ, luôn cần sử dụng |
| **On demand** | Client gọi factory khi một thao tác cần sản phẩm | Tránh tạo sản phẩm chưa dùng |
| **Cached/pooled** | Factory trả sản phẩm/handle có sẵn hoặc dùng lại | Phù hợp với một số sản phẩm không có state độc lập hoặc tài nguyên được quản lý đặc biệt |

Trong ví dụ, `SettingsScreen` **nhận factory ở constructor nhưng tạo sản phẩm trong `show()`**. Vì vậy, việc truyền factory chưa sinh ra `LightButton` hoặc `DarkButton`.

Nếu product cần giữ trạng thái qua nhiều lần render, client có thể lưu sản phẩm thành field và chỉ tạo một lần. Nếu đổi họ trong khi client vẫn giữ những field đó, sản phẩm cũ **không tự biến thành sản phẩm của họ mới**; ứng dụng phải xác định cách tái tạo hoặc thay toàn bộ bộ sản phẩm.

Không nên đưa ra kết luận “mỗi lần gọi factory đều có `new`” nếu contract của factory thực tế cho phép cache hoặc pool. Ví dụ dùng `new` để minh họa rõ đường đi, còn việc chia sẻ instance phải được quyết định từ yêu cầu nghiệp vụ và vòng đời.

## 8. Bẫy trộn họ: client vượt qua ranh giới Abstract Factory

Giả sử client gọi:

~~~java
UiFactory factory = new LightUiFactory();
Button button = factory.createButton();

// Cách viết cần tránh khi client phải dùng một họ nhất quán:
Checkbox checkbox = new DarkCheckbox();
~~~

Button thuộc Light nhưng Checkbox thuộc Dark. Dù cả hai đều đúng interface và có thể render riêng lẻ, giao diện có nguy cơ sai màu sắc, theme token hoặc tương tác không đồng bộ.

Cách tổ chức đúng với yêu cầu cùng họ:

~~~java
UiFactory factory = new LightUiFactory();
Button button = factory.createButton();
Checkbox checkbox = factory.createCheckbox();
~~~

Nhìn từ trace, các phương thức cấp phát cho hai loại sản phẩm đều phải đi qua **cùng một concrete factory được chọn** (hoặc qua một đối tượng factory/scope được định nghĩa là cùng họ). Nếu bạn thấy client vừa gọi `LightUiFactory.createButton()` vừa gọi `new DarkCheckbox()` thì đường tạo product đã bị tách khỏi hợp đồng họ sản phẩm.

Việc compiler cho phép gán `DarkCheckbox` vào biến `Checkbox` không đảm bảo nó phù hợp với **họ** mà client đang dùng. Type safety của interface và tính nhất quán họ là hai điều kiện khác nhau.

## 9. Quan sát call stack bằng debugger

Khi đang học hoặc điều tra một lỗi tạo sản phẩm sai, đặt các breakpoint theo thứ tự sau:

1. **`main()` hoặc cấu hình DI:** Xem concrete factory nào được chọn và được truyền cho client.
2. **`SettingsScreen` constructor:** Xác nhận client giữ tham chiếu `UiFactory` nhận từ bên ngoài.
3. **`SettingsScreen.show()` tại `factory.createButton()`:** Dùng Step Into để đi vào phương thức thực thi.
4. **`LightUiFactory.createButton()` hoặc `DarkUiFactory.createButton()`:** Xác nhận dòng tạo và trả product.
5. **Constructor của concrete product (nếu có):** Xem cấu hình/style/resource nào được cấp cho sản phẩm.
6. **`button.render()` trong client:** Dùng Step Into một lần nữa để đến `LightButton.render()` hoặc `DarkButton.render()`.
7. **`factory.createCheckbox()` và `checkbox.render()`:** Lặp lại, kiểm tra hai sản phẩm cùng họ.

Hai quan sát đặc biệt hữu ích:

- Khi đứng tại dòng `factory.createButton()`, xem **runtime class** của `factory`; kiểu biến `UiFactory` chưa nói factory đang là Light hay Dark.
- Khi đứng tại dòng `button.render()`, xem **runtime class** của `button`; kiểu biến `Button` chưa nói concrete product đang được gọi.

Trong một debugger Java, có thể đánh giá `factory.getClass().getName()` và `button.getClass().getName()` chỉ để quan sát. Đây là thao tác hỗ trợ debug; tránh dùng reflection hay so tên class trong logic nghiệp vụ chỉ để xác định họ sản phẩm.

### Khi ứng dụng có dependency injection container

DI container có thể thay `new LightUiFactory()` tại `main()` bằng một bước resolve dependency. Call graph vẫn là:

`composition root / container → concrete factory được chọn → client nhận interface → factory method → concrete product → product method`.

Hãy kiểm tra **binding** ở container, vì một cấu hình DI sai có thể chọn nhầm concrete factory trong khi tất cả lời gọi sau đó đều hợp lệ về kiểu.

## 10. Theo dõi luồng trong ứng dụng thực bằng log

`System.out.println` phù hợp để học, nhưng trong ứng dụng có nhiều request, task đồng thời hoặc nhiều màn hình, log cần đủ ngữ cảnh để ghép đúng các sự kiện thuộc cùng một luồng.

Một bản ghi hữu ích có thể gồm:

| Trường | Ví dụ minh họa | Dùng để làm gì |
| --- | --- | --- |
| `operationId` | `settings-42` | Ghép các dòng thuộc cùng lần dựng màn hình |
| `selectedFamily` | `dark` | Xác định họ ứng dụng chọn ở composition root |
| `factoryType` | `DarkUiFactory` | Phân biệt factory thực thi |
| `productType` | `Button` | Biết phương thức tạo loại sản phẩm nào |
| `productImplementation` | `DarkButton` | Kiểm tra lớp sản phẩm được trả về |
| `event` | `create-start`, `create-success`, `render` | Đọc thứ tự và trạng thái của luồng |
| `outcome` | `success` hoặc loại lỗi | Phân biệt tạo thành công với tạo thất bại |

Ví dụ chuỗi sự kiện giả định:

~~~text
op=settings-42 family=dark event=factory-selected factory=DarkUiFactory
op=settings-42 event=create-start product=Button
op=settings-42 event=create-success product=Button impl=DarkButton
op=settings-42 event=create-start product=Checkbox
op=settings-42 event=create-success product=Checkbox impl=DarkCheckbox
op=settings-42 event=render product=Button impl=DarkButton
op=settings-42 event=render product=Checkbox impl=DarkCheckbox
~~~

Trong code production, dùng logger phù hợp, tránh ghi dữ liệu nhạy cảm của người dùng và cân nhắc độ ồn/performance. Log dùng để quan sát; nguồn quyết định correctness vẫn là hợp đồng của hệ thống và các bài kiểm thử.

Nếu factory mở tài nguyên hoặc gọi mạng bất đồng bộ, thêm thời điểm bắt đầu/kết thúc, correlation ID và thông tin lỗi. Khi đó **thứ tự hoàn tất** có thể khác **thứ tự bắt đầu**, nên không suy ra quan hệ nhân quả chỉ từ timestamp nếu thiếu correlation.

## 11. Kiểm thử thứ tự lời gọi mà không phụ thuộc UI thật

Có thể viết một **recording factory** để xác nhận client yêu cầu đúng các sản phẩm, sau đó gọi đúng product interface. Ví dụ JUnit 5 dưới đây dùng lớp `AbstractFactoryTraceDemo` từ mục 4. Đặt test trong cùng package, trong file `AbstractFactoryTraceDemoTest.java`.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;

class AbstractFactoryTraceDemoTest {
    @Test
    void client_asks_factory_before_using_its_products() {
        List<String> events = new ArrayList<>();

        AbstractFactoryTraceDemo.UiFactory recordingFactory =
            new AbstractFactoryTraceDemo.UiFactory() {
                @Override
                public AbstractFactoryTraceDemo.Button createButton() {
                    events.add("factory.createButton");
                    return () -> events.add("button.render");
                }

                @Override
                public AbstractFactoryTraceDemo.Checkbox createCheckbox() {
                    events.add("factory.createCheckbox");
                    return () -> events.add("checkbox.render");
                }
            };

        new AbstractFactoryTraceDemo.SettingsScreen(recordingFactory)
            .show();

        assertEquals(List.of(
            "factory.createButton",
            "factory.createCheckbox",
            "button.render",
            "checkbox.render"
        ), events);
    }
}
~~~

Test này xác nhận **thứ tự cộng tác do client quyết định**, nhưng không chứng minh `LightUiFactory` thực sự tạo `LightButton`. Để kiểm tra nhánh khởi tạo thật, viết thêm test dùng **concrete factory** và kiểm tra kết quả quan sát được hoặc thuộc tính định danh họ theo hợp đồng của ứng dụng.

Cần phân biệt:

- **Trace test:** Client gửi lời gọi đúng thứ tự tới factory và product.
- **Factory/product contract test:** Mỗi concrete factory trả sản phẩm đúng loại/họ; mỗi product thực hiện đúng hành vi interface.
- **Integration test:** Cả họ sản phẩm cộng tác đúng khi chạy một luồng thực.

Một trace trông hợp lý không tự chứng minh hoạt động nghiệp vụ đúng; nó chỉ cho thấy đường đi của lời gọi.

## 12. Chẩn đoán một số lỗi thường gặp qua trace

| Triệu chứng | Vị trí cần kiểm tra | Câu hỏi chẩn đoán |
| --- | --- | --- |
| Chọn Dark nhưng màn hình là Light | Composition root / DI binding | Runtime factory thật có phải `DarkUiFactory` không? |
| Factory đúng nhưng Button sai họ | `createButton()` của concrete factory | Factory trả về lớp product nào? Có dùng config/cache cũ không? |
| Button đúng họ nhưng Checkbox sai họ | `createCheckbox()` | Hai lời gọi có dùng cùng family context không? |
| Không thấy product nào được tạo | Thời điểm client gọi factory | Client chỉ nhận factory hay đã gọi `show()`? Có lazy creation không? |
| Product tạo được nhưng không render | Sau khi factory trả về | Client có gọi `render()`? Có nhánh điều kiện chặn không? |
| Đổi cấu hình nhưng giao diện chưa đổi | Vòng đời của client/product | Client đang giữ tham chiếu product cũ hay factory cũ? |
| Log nhiều request trộn vào nhau | Correlation ID | Các sự kiện đang thuộc cùng operation hay hai operation khác nhau? |
| Client tự `new` product | Ranh giới abstraction | Vì sao client biết concrete class thay vì dùng factory? |

Một cách gỡ lỗi hiệu quả là khoanh vùng **lần chuyển giao đầu tiên không đúng với kỳ vọng**:

- Factory được chọn sai → kiểm tra cấu hình hoặc dependency injection.
- Factory được chọn đúng nhưng product trả về sai → kiểm tra concrete factory hoặc cache.
- Product trả về đúng nhưng thao tác sai → kiểm tra concrete product hoặc client.
- Mọi lời gọi đơn lẻ đúng nhưng toàn màn hình sai → kiểm tra tính nhất quán họ và vòng đời sản phẩm.

## 13. Bài tập: lần theo luồng tạo tài liệu xuất báo cáo

Giả sử ứng dụng xuất báo cáo hỗ trợ hai họ:

- `PdfExportFactory` tạo `PdfHeader` và `PdfTable`.
- `HtmlExportFactory` tạo `HtmlHeader` và `HtmlTable`.
- Client `ReportPage` nhận `ExportFactory`, gọi `createHeader()`, `createTable()` rồi gọi `render()` trên mỗi sản phẩm.

Hãy tự thực hiện:

1. Vẽ sequence diagram của luồng khi bootstrap chọn `PdfExportFactory`.
2. Viết trace dự kiến cho lần chạy PDF và HTML, chỉ đổi factory ở composition root.
3. Đánh dấu hai điểm dynamic dispatch: lời gọi trên `ExportFactory` và lời gọi trên product interface.
4. Dự đoán điều gì xảy ra nếu `PdfExportFactory.createTable()` trả về `HtmlTable`.
5. Cho biết đặt breakpoint nào nếu config nói `pdf` nhưng client lại render `HtmlHeader`.
6. Sửa thiết kế để client không cần gọi `new PdfHeader()` hoặc `new HtmlTable()`.

**Gợi ý kiểm tra:** Ở nhánh PDF, client phải nhận lần lượt `PdfHeader`, `PdfTable`; ở nhánh HTML, nhận `HtmlHeader`, `HtmlTable`. Nếu header và table thuộc hai họ khác nhau, các interface vẫn có thể hợp lệ nhưng family invariant bị vi phạm. Nên kiểm tra từ composition root đến phương thức của concrete factory đã trả ra sản phẩm sai trước khi điều tra `render()`.

## 14. Ghi nhớ

Khi theo dõi luồng khởi tạo trong Abstract Factory, luôn phân biệt **ba vị trí**: nơi **chọn concrete factory**, nơi **client gọi abstract factory để yêu cầu product**, và nơi **client dùng product qua interface**. Một lời gọi factory method tạo hoặc cung cấp concrete product; lời gọi thao tác trên product sau đó được phân giải theo runtime type của product ấy.

Trong ví dụ Light/Dark, thay `LightUiFactory` bằng `DarkUiFactory` ở composition root khiến cùng một `SettingsScreen` nhận và sử dụng sản phẩm của họ khác. Sequence diagram, log và debugger giúp kiểm tra từng mắt xích; contract test và integration test giúp xác nhận những mắt xích đó thực hiện đúng hành vi mà hệ thống mong đợi.
