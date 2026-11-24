# Đăng ký, hủy và dọn dẹp luồng theo vòng đời giao diện

Ứng dụng trình duyệt thường chỉ cần nhận dữ liệu realtime khi một màn hình đang hiển thị. Ví dụ, trang chi tiết đơn hàng đăng ký luồng cập nhật trạng thái khi người dùng mở trang và dừng nhận dữ liệu khi họ rời đi. Nếu mỗi lần render lại tạo thêm một subscription, hoặc component đã unmount nhưng stream vẫn chạy, ứng dụng có thể nhận sự kiện trùng, cập nhật state đã hết vòng đời và giữ tài nguyên mạng không cần thiết.

Với RSocket, client gọi request-stream hoặc request-channel để nhận dữ liệu bất đồng bộ. Subscription của stream có vòng đời riêng, độc lập với kết nối RSocket bên dưới. Vì vậy cần quản lý hai lớp:

- **Kết nối RSocket:** thường được chia sẻ ở cấp ứng dụng hoặc phiên đăng nhập.
- **Subscription của giao diện:** được tạo khi màn hình cần dữ liệu và bị hủy khi màn hình không còn cần.

Khi component rời màn hình, hãy hủy subscription tương ứng bằng cancellation. Chỉ đóng kết nối RSocket khi chủ sở hữu kết nối không còn consumer nào hoặc ứng dụng đang kết thúc phiên.

## 1. Vòng đời giao diện và vòng đời stream

Một màn hình theo dõi đơn hàng có thể trải qua các bước:

1. Component được mount và nhận mã đơn hàng cần theo dõi.
2. Ứng dụng lấy một RSocket connection đang hoạt động từ connection manager.
3. Client gửi request-stream tới route orders.events.
4. Server phát các sự kiện trạng thái; client cập nhật giao diện.
5. Khi component unmount hoặc mã đơn hàng thay đổi, client hủy stream cũ.
6. Nếu cần theo dõi đơn hàng khác, component đăng ký stream mới với request mới.

~~~mermaid
sequenceDiagram
    participant UI as Order screen
    participant M as Connection manager
    participant C as RSocket client
    participant S as RSocket server
    UI->>M: acquire connection
    M-->>UI: shared RSocket socket
    UI->>C: requestStream(orders.events)
    C->>S: REQUEST_STREAM
    loop Màn hình còn hoạt động
        S-->>C: PAYLOAD OrderEvent
        C-->>UI: onNext(event)
    end
    UI->>C: subscription.cancel()
    C->>S: CANCEL (stream ID)
    Note over S: Dừng nguồn dữ liệu và dọn tài nguyên của stream
    Note over M,C: Kết nối dùng chung vẫn có thể phục vụ màn hình khác
~~~

Việc hủy stream không nhất thiết đóng socket. Một kết nối RSocket có thể multiplex nhiều stream; hủy một stream chỉ kết thúc tương tác tương ứng.

## 2. Phân biệt connect, subscribe và cancel

Ba thao tác này có ý nghĩa khác nhau:

| Thao tác | Phạm vi | Ý nghĩa |
|---|---|---|
| Connect | Kết nối RSocket | Mở transport và thiết lập phiên RSocket |
| Subscribe | Một tương tác/stream | Bắt đầu nhận dữ liệu từ request-stream hoặc request-channel |
| Cancel | Một subscription | Yêu cầu dừng stream cụ thể đang hoạt động |
| Close connection | Toàn bộ phiên | Đóng RSocket socket và các tương tác còn lại |

Nếu một trang web mở kết nối RSocket dùng chung, mỗi component chỉ nên quản lý subscription mà component đó tạo. Component không nên gọi close connection trong cleanup nếu các component khác vẫn dùng cùng socket.

Connection manager có thể cung cấp một lease hoặc reference count. Mỗi màn hình acquire một lease khi cần socket và release lease khi kết thúc. Manager chỉ đóng kết nối khi không còn consumer và chính sách ứng dụng cho phép đóng.

## 3. Đăng ký request-stream trong trình duyệt

Trong trình duyệt, RSocket thường chạy trên WebSocket vì mã JavaScript trong trang không thể tự mở raw TCP socket tới server. Client kết nối bằng WebSocket hoặc secure WebSocket (WSS), hoàn tất setup RSocket rồi mới gọi các interaction. Bài này giả định connection manager đã thiết lập socket bằng transport phù hợp.

RSocket JavaScript cung cấp request-stream dưới dạng Flowable. Khi subscribe, client nhận một Subscription; có thể gọi request(n) để yêu cầu số phần tử và cancel() để hủy tương tác.

Ví dụ sau dùng các hàm encode/decode do ứng dụng định nghĩa để chuyển request và payload theo codec đã thống nhất với server:

~~~javascript
function watchOrderEvents(socket, orderId, onEvent, onError) {
  let streamSubscription;

  socket.requestStream(encodeOrderEventsRequest(orderId)).subscribe({
    onSubscribe(subscription) {
      streamSubscription = subscription;
      subscription.request(1);
    },
    onNext(payload) {
      try {
        onEvent(decodeOrderEvent(payload));
      } catch (error) {
        streamSubscription?.cancel();
        onError(error);
        return;
      }

      // Chỉ yêu cầu phần tử tiếp theo sau khi xử lý phần tử hiện tại.
      streamSubscription?.request(1);
    },
    onError(error) {
      onError(error);
    },
    onComplete() {
      // Server đã hoàn tất luồng một cách bình thường.
    }
  });

  return () => streamSubscription?.cancel();
}
~~~

encodeOrderEventsRequest và decodeOrderEvent là adapter của ứng dụng. Chúng phải dùng đúng data MIME type, metadata MIME type và route mà server mong đợi. Đoạn code tập trung vào vòng đời Flowable: nhận Subscription, phát demand, xử lý phần tử và trả về hàm cleanup.

Không nên gọi request(Infinity) cho một luồng dài nếu giao diện không thể xử lý dữ liệu với tốc độ tương ứng. Yêu cầu một phần tử mỗi lần là cách đơn giản để minh họa demand có kiểm soát. Với tải lớn, có thể yêu cầu theo batch và dùng hàng đợi có giới hạn.

## 4. Gắn subscription với vòng đời React

Trong React, useEffect phù hợp để đồng bộ component với một subscription bên ngoài. Effect tạo stream khi dependency thay đổi; hàm cleanup hủy stream trước khi effect chạy lại hoặc component unmount.

Ví dụ giả định connectionManager.acquire() trả về một lease có socket và release(). Manager quản lý kết nối dùng chung; component chỉ sở hữu stream của chính nó.

~~~jsx
import { useEffect, useState } from "react";

export function OrderEvents({ connectionManager, orderId }) {
  const [events, setEvents] = useState([]);
  const [error, setError] = useState(null);
  const [finished, setFinished] = useState(false);

  useEffect(() => {
    let disposed = false;
    let lease;
    let streamSubscription;

    setError(null);
    setFinished(false);
    setEvents([]);

    connectionManager.acquire()
      .then((acquiredLease) => {
        if (disposed) {
          acquiredLease.release();
          return;
        }

        lease = acquiredLease;
        lease.socket
          .requestStream(encodeOrderEventsRequest(orderId))
          .subscribe({
            onSubscribe(subscription) {
              streamSubscription = subscription;
              subscription.request(1);
            },
            onNext(payload) {
              if (disposed) return;
              try {
                const event = decodeOrderEvent(payload);
                setEvents((current) => [...current, event]);
              } catch (decodeError) {
                setError(decodeError);
                streamSubscription?.cancel();
                return;
              }
              streamSubscription?.request(1);
            },
            onError(streamError) {
              if (!disposed) setError(streamError);
            },
            onComplete() {
              if (!disposed) setFinished(true);
            }
          });
      })
      .catch((connectionError) => {
        if (!disposed) setError(connectionError);
      });

    return () => {
      disposed = true;
      streamSubscription?.cancel();
      lease?.release();
    };
  }, [connectionManager, orderId]);

  return (
    <section>
      <h2>Trạng thái đơn hàng {orderId}</h2>
      {error && <p role="alert">Không thể nhận cập nhật.</p>}
      {finished && <p>Luồng cập nhật đã kết thúc.</p>}
      <ul>
        {events.map((event) => (
          <li key={event.sequence}>
            {event.status}
          </li>
        ))}
      </ul>
    </section>
  );
}
~~~

Điểm quan trọng:

- Biến disposed ngăn callback cập nhật state sau khi component đã rời màn hình.
- streamSubscription.cancel() dừng đúng request-stream mà component đã đăng ký.
- lease.release() báo cho connection manager rằng component không còn sử dụng socket.
- Effect phụ thuộc vào connectionManager và orderId; khi orderId đổi, stream cũ được cleanup trước khi stream mới được tạo.
- Cleanup không tự gọi socket.close(), vì socket có thể đang được component khác sử dụng.

Trong ví dụ, events được reset khi orderId thay đổi để không trộn lịch sử của hai đơn hàng. Nếu màn hình cần quay lại lịch sử trước đó, hãy lưu state theo orderId. Dù chọn cách nào, nên giới hạn số event giữ trong state để tránh tăng bộ nhớ vô hạn trên màn hình mở lâu.

## 5. Tránh đăng ký lặp do render

Không tạo subscription trực tiếp trong phần thân function component:

~~~jsx
// Không nên: mỗi lần render có thể tạo thêm một stream.
function OrderEvents({ socket, orderId }) {
  socket.requestStream(encodeOrderEventsRequest(orderId))
    .subscribe({
      onNext: (payload) => console.log(payload)
    });

  return <div>Watching order</div>;
}
~~~

React có thể render component nhiều lần do state, props, parent render hoặc chế độ kiểm tra trong môi trường development. Đặt subscribe trong render khiến mỗi lần render có thể mở một stream mới, trong khi không có cleanup gắn với subscription.

Hãy tạo subscription trong useEffect hoặc một hook chuyên trách có cleanup. Giữ connectionManager ổn định bằng context/provider hoặc một service singleton có lifecycle rõ ràng; nếu tạo một object manager mới ở mỗi render, effect sẽ liên tục cleanup và đăng ký lại.

React Strict Mode trong development có thể chạy chu kỳ setup-cleanup-setup để phát hiện side effect thiếu cleanup. Một subscription được quản lý đúng phải chịu được chu kỳ này mà không để lại stream cũ.

## 6. Khi tham số màn hình thay đổi

Giả sử component đang theo dõi ORD-1001 và người dùng chuyển sang ORD-1002. Effect sẽ chạy cleanup của stream cũ, sau đó đăng ký stream mới. Cleanup phải hủy subscription trước khi request mới được bắt đầu để tránh nhận sự kiện từ cả hai đơn hàng cùng lúc.

Nếu callback bất đồng bộ hoàn tất sau cleanup, cờ disposed ngăn nó thay đổi state. Nếu ứng dụng cần phân biệt rõ dữ liệu cũ và mới, có thể gắn orderId vào mỗi event và kiểm tra trước khi cập nhật.

Đừng dùng một biến subscription toàn cục cho mọi component. Hai màn hình có thể theo dõi hai route khác nhau trên cùng socket; mỗi component cần giữ handle của stream riêng.

## 7. Hủy stream và backpressure ở trình duyệt

Flowable của RSocket JS sử dụng demand để điều tiết số payload được chuyển tới subscriber. Client có thể:

- Yêu cầu một phần tử với request(1) rồi yêu cầu phần tiếp theo sau khi xử lý xong.
- Yêu cầu một batch nhỏ nếu UI có thể xử lý theo lô.
- Tạm dừng yêu cầu phần tử mới khi tab hoặc màn hình không thể xử lý dữ liệu.
- Gọi cancel() khi component không còn quan tâm đến stream.

Nếu xử lý payload bất đồng bộ, không nên tăng demand ngay khi bắt đầu xử lý. Có thể yêu cầu phần tử tiếp theo sau khi thao tác hiện tại hoàn tất:

~~~javascript
onNext(payload) {
  processEvent(decodeOrderEvent(payload))
    .then(() => streamSubscription.request(1))
    .catch((error) => {
      streamSubscription.cancel();
      reportProcessingError(error);
    });
}
~~~

Ví dụ này giả định processEvent trả về Promise và subscriber đã lưu streamSubscription. Với nhiều phần tử đang được xử lý song song, hãy giới hạn số tác vụ đồng thời và số phần tử chờ. Backpressure ở tầng RSocket không tự giới hạn một hàng đợi JavaScript mà ứng dụng tự tạo không giới hạn.

## 8. Server cần phản ứng với CANCEL

Khi client hủy một request-stream, RSocket gửi frame CANCEL cho stream tương ứng. Phía server cần để cancellation truyền tới publisher và nguồn dữ liệu bên dưới.

Ví dụ handler Spring:

~~~java
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Flux;
import reactor.core.publisher.SignalType;

@Controller
public class OrderEventsController {

    private final OrderEventService eventService;

    public OrderEventsController(OrderEventService eventService) {
        this.eventService = eventService;
    }

    @MessageMapping("orders.events")
    public Flux<OrderEvent> watch(OrderEventsRequest request) {
        return eventService.watch(request.orderId())
            .doFinally(signal -> {
                if (signal == SignalType.CANCEL) {
                    log.debug("Order event stream cancelled: {}",
                        request.orderId());
                }
            });
    }
}
~~~

doFinally được gọi khi stream complete, error hoặc cancel. Có thể dùng nó để ghi metric và log vòng đời. Nếu nguồn dữ liệu mở tài nguyên cần đóng bất đồng bộ, hãy dùng cơ chế quản lý tài nguyên như Flux.usingWhen để bảo đảm cleanup ở cả ba đường kết thúc.

Ví dụ quản lý một subscription tới event source:

~~~java
public Flux<OrderEvent> watch(String orderId) {
    return Flux.usingWhen(
        eventSource.open(orderId),
        handle -> handle.events(),
        EventHandle::close,
        (handle, error) -> handle.close(),
        EventHandle::close
    );
}
~~~

EventHandle và eventSource là abstraction do ứng dụng định nghĩa. close() trả về Publisher<Void> để việc dọn dẹp bất đồng bộ được hoàn tất. Khi client cancel, usingWhen gọi nhánh cleanup tương ứng; nếu không quản lý resource, consumer hoặc listener có thể còn tồn tại sau khi UI đã rời màn hình.

Cancellation chỉ yêu cầu dừng tương tác. Nó không thể đảo ngược tác dụng phụ mà server đã thực hiện trước khi nhận CANCEL. Vì vậy request-stream theo dõi dữ liệu nên ưu tiên thao tác đọc; với thao tác ghi, cần thiết kế idempotency và xác nhận kết quả riêng.

## 9. Phân biệt cancel, complete và error

Ba tín hiệu kết thúc cần được xử lý khác nhau:

| Tín hiệu | Ai khởi tạo? | Ý nghĩa ở UI | Xử lý phù hợp |
|---|---|---|---|
| Cancel | Subscriber/client | Người dùng rời màn hình hoặc không cần dữ liệu nữa | Dừng stream, giải phóng tài nguyên |
| Complete | Publisher/server | Nguồn dữ liệu đã phát xong bình thường | Đánh dấu hoàn tất; không tự coi là lỗi |
| Error | Publisher hoặc transport | Không thể tiếp tục nhận dữ liệu | Hiển thị lỗi, ghi log và cân nhắc reconnect |

Khi component unmount, cleanup chủ động gọi cancel. Không cần cập nhật UI thành trạng thái lỗi chỉ vì chính component đã hủy subscription. Callback onError có thể xuất hiện do lỗi thật trước khi cleanup; hãy kiểm tra disposed để không cập nhật state sau unmount.

## 10. Quản lý kết nối dùng chung bằng lease

Một ứng dụng có thể có nhiều màn hình cùng dùng một RSocket socket. Connection manager nên tách trách nhiệm quản lý socket khỏi trách nhiệm quản lý stream:

~~~javascript
class RSocketConnectionManager {
  constructor(connect) {
    this.connect = connect;
    this.socketPromise = null;
    this.references = 0;
  }

  async acquire() {
    this.references += 1;

    try {
      if (!this.socketPromise) {
        this.socketPromise = this.connect().catch((error) => {
          this.socketPromise = null;
          throw error;
        });
      }

      const socket = await this.socketPromise;
      let released = false;

      return {
        socket,
        release: () => {
          if (released) return;
          released = true;
          this.references -= 1;
          // Chính sách đóng socket được quyết định ở cấp manager.
        }
      };
    } catch (error) {
      this.references -= 1;
      throw error;
    }
  }
}
~~~

Đây là skeleton minh họa ownership; triển khai production cần xử lý race khi nhiều acquire cùng lúc, socket bị đóng, connect thất bại và reconnect. Khi references về 0, manager có thể giữ socket trong một khoảng idle để tái sử dụng hoặc đóng socket theo chính sách ứng dụng. Không đóng socket chỉ vì một component release nếu vẫn còn lease khác.

Khi người dùng đăng xuất, manager cần hủy các stream thuộc phiên người dùng, đóng kết nối theo chính sách bảo mật và xóa credential khỏi bộ nhớ. Khi chuyển tài khoản, không tái sử dụng một session đã mang danh tính cũ nếu mô hình xác thực của ứng dụng gắn identity ở cấp SETUP.

## 11. Reconnect và đăng ký lại stream

Nếu transport bị lỗi, stream hiện tại kết thúc bằng error. Subscription đã kết thúc không tự hoạt động trở lại chỉ vì connection manager mở socket mới. Ứng dụng phải quyết định có đăng ký lại hay không.

Với một luồng sự kiện có sequence number, có thể lưu sequence cuối cùng đã xử lý và gửi nó trong request tiếp theo:

~~~javascript
let lastProcessedSequence = 0;

function subscribeFrom(socket, orderId) {
  let streamSubscription;

  socket.requestStream(
    encodeOrderEventsRequest({
      orderId,
      afterSequence: lastProcessedSequence
    })
  ).subscribe({
    onSubscribe(subscription) {
      streamSubscription = subscription;
      subscription.request(1);
    },
    onNext(payload) {
      const event = decodeOrderEvent(payload);
      applyEvent(event);
      lastProcessedSequence = event.sequence;
      streamSubscription?.request(1);
    },
    onError(error) {
      scheduleReconnectAndResubscribe(error);
    }
  });

  return () => streamSubscription?.cancel();
}
~~~

Đoạn code mô tả ý tưởng cursor; trong triển khai thật cần giữ tham chiếu Subscription trong scope để cancel và yêu cầu demand đúng cách. Cursor chỉ nên được cập nhật sau khi sự kiện đã được áp dụng thành công. Nếu client xử lý xong nhưng chưa lưu cursor, server có thể phát lại sự kiện; handler cần chịu được duplicate.

Reconnect và resubscribe là phục hồi ở tầng ứng dụng. RSocket Resume, nếu được cấu hình và hỗ trợ ở cả hai đầu, có thể khôi phục session và các stream còn trong trạng thái lưu giữ. Nếu resume thất bại hoặc client khởi động lại, ứng dụng vẫn cần cơ chế cursor/replay nghiệp vụ để phục hồi dữ liệu.

Khi retry kết nối, dùng backoff có giới hạn và jitter để tránh nhiều tab hoặc nhiều client cùng reconnect dồn dập. Hãy tránh tạo nhiều vòng reconnect đồng thời cho cùng một connection manager.

## 12. Tab nền, điều hướng và đóng trình duyệt

Trình duyệt có thể giảm tần suất timer hoặc tạm dừng một số công việc khi tab ở nền. Ứng dụng cần quyết định theo yêu cầu sản phẩm:

- Tiếp tục giữ stream nếu người dùng cần nhận dữ liệu ngay khi quay lại.
- Hủy stream khi tab ẩn nếu dữ liệu có thể lấy lại bằng snapshot hoặc cursor.
- Giữ kết nối nhưng tạm giảm demand nếu muốn tiết kiệm xử lý.
- Khi tab visible trở lại, kiểm tra socket còn hoạt động; nếu không, reconnect và resubscribe.

Không dựa hoàn toàn vào beforeunload để dọn dẹp. Trình duyệt có thể đóng tab đột ngột hoặc giới hạn thời gian chạy handler. Cleanup trong lifecycle của component, quản lý connection ở cấp ứng dụng và timeout phía server vẫn cần thiết.

Nếu dùng nhiều tab, mỗi tab có thể có một connection riêng hoặc chia sẻ một connection qua cơ chế phối hợp như SharedWorker. Dù chọn cách nào, phải xác định rõ ai sở hữu socket và ai được quyền đóng nó. Một tab không được đóng kết nối đang phục vụ tab khác.

## 13. Tránh lỗi stale callback và dữ liệu cũ

Callback của stream có thể chạy sau khi props đã đổi hoặc component đã unmount. Cờ disposed ngăn cập nhật state sau cleanup, nhưng với pipeline phức tạp có thể cần thêm generation ID:

~~~javascript
let generation = 0;

function startWatching(orderId) {
  const currentGeneration = ++generation;

  return subscribeToOrder(orderId, (event) => {
    if (currentGeneration !== generation) return;
    renderEvent(event);
  });
}

function stopWatching(cancel) {
  generation += 1;
  cancel();
}
~~~

Generation ID giúp bỏ qua callback đến muộn từ subscription cũ sau khi một subscription mới đã bắt đầu. Không thay thế cancel; nó chỉ là lớp bảo vệ bổ sung ở phía UI.

Khi stream phát dữ liệu nhanh, tránh nối mảng state vô hạn. Có thể giữ N sự kiện mới nhất, gom dữ liệu theo batch hoặc dùng store có giới hạn. Nếu giao diện chỉ cần trạng thái mới nhất, có thể ghi đè snapshot thay vì giữ toàn bộ lịch sử.

## 14. Kiểm thử đăng ký, hủy và cleanup

Một bộ kiểm thử nên xác nhận hành vi ở cả client và server:

1. Mount màn hình tạo đúng một subscription cho route cần theo dõi.
2. Render lại không tạo subscription mới ngoài ý muốn.
3. Đổi orderId hủy stream cũ trước khi đăng ký stream mới.
4. Unmount gọi cancel đúng một lần và không cập nhật state sau cleanup.
5. Release lease không đóng socket khi còn component khác đang dùng.
6. Server nhận CANCEL và dừng publisher hoặc giải phóng event listener.
7. Server complete tự nhiên được hiển thị khác với error.
8. Transport lỗi dẫn tới reconnect có giới hạn và resubscribe từ cursor.
9. Sự kiện phát lại không làm trạng thái nghiệp vụ bị áp dụng hai lần.
10. Nhiều component theo dõi các route khác nhau mà không hủy nhầm subscription của nhau.

Ở phía server, có thể dùng StepVerifier để kiểm tra cancellation:

~~~java
StepVerifier.create(controller.watch(
        new OrderEventsRequest("ORD-1002")
    ))
    .thenRequest(1)
    .expectNextCount(1)
    .thenCancel()
    .verify();
~~~

Để xác nhận cleanup thực sự chạy, gắn một counter hoặc mock vào resource handle và kiểm tra close() được gọi sau cancellation. Integration test qua transport thật có thể bổ sung xác nhận CANCEL được chuyển tới server và nguồn dữ liệu được giải phóng.

Ở phía trình duyệt, dùng test framework của UI để mount/unmount component và mock Flowable. Kiểm tra subscription.cancel() được gọi, lease.release() được gọi và callback đến muộn không làm thay đổi state sau unmount.

## 15. Checklist triển khai

Trước khi đưa stream realtime vào một màn hình, hãy xác nhận:

- Connection manager có ownership rõ ràng và được chia sẻ ở đúng cấp.
- Mỗi component giữ handle subscription riêng.
- Đăng ký stream nằm trong lifecycle hook/effect, không nằm trong render.
- Cleanup hủy subscription và release lease.
- Chỉ connection manager hoặc chủ sở hữu mới đóng socket.
- Client phát demand có giới hạn và xử lý lỗi/complete riêng biệt.
- Server phản ứng với CANCEL và dọn tài nguyên upstream.
- Reconnect không tạo vòng lặp vô hạn hoặc nhiều kết nối trùng.
- Resubscribe có cursor/sequence nếu cần tránh mất dữ liệu.
- UI giới hạn bộ nhớ và bỏ qua callback stale.

## 16. Kết luận

Đăng ký và hủy stream phải gắn với vòng đời của giao diện. Component tạo request-stream khi cần dữ liệu, giữ Subscription để điều tiết demand và gọi cancel khi unmount hoặc khi tham số theo dõi thay đổi. Server cần truyền cancellation tới publisher và giải phóng listener, consumer hoặc tài nguyên liên quan.

Kết nối RSocket thường thuộc quyền quản lý của ứng dụng hoặc session, còn từng stream thuộc component sử dụng nó. Tách hai vòng đời này giúp nhiều màn hình chia sẻ socket an toàn, tránh đăng ký trùng và không đóng nhầm kết nối. Khi cần phục hồi sau lỗi mạng, reconnect và resubscribe phải dùng chính sách riêng, có cursor nếu cần replay dữ liệu chính xác.
