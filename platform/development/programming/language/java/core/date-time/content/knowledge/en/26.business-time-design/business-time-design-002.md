# Distinguishing Occurred Events from Future Appointments

## 1. One records a fact, the other preserves an intent

“When did the transaction happen?” requires a point on the timeline. “The customer wants to meet at 09:00 in Berlin” requires preserving an intent based on a local wall clock and location. If both are stored in an ambiguous field like `timestamp`, processing code can easily overwrite history by mistake or cause the appointment time to drift.

The distinction lies in **business semantics**, not merely whether the value is earlier or later than `now`. A future deadline can be fixed in UTC; a past appointment still retains its planned schedule data and may never have actually taken place.

| Question | Usually suitable model |
| --- | --- |
| When did something actually occur? | `Instant occurredAt` |
| When did the system receive the information? | `Instant receivedAt` or `recordedAt` |
| Appointment by clock time at a location | `LocalDateTime` + `ZoneId` + resolution policy |
| A future event occurring simultaneously worldwide | `Instant` as the fixed point |
| Weekly at 09:00 at a location | Recurrence rule + local time + zone |

## 2. Occurred events: preserve the actual instant

`Instant` represents a point in time independent of how it is displayed in different time zones. The same payment may be viewed as 09:00 in Berlin and 14:00 in Vietnam, yet it remains a single instant. [Instant](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Instant.html)

When context is needed, you can additionally store the zone, offset, or source timestamp string. Those fields serve display or traceability; changing a viewer's time zone must never modify `occurredAt`.

Distinguish between occurrence time and receipt time. A device sending data late, a congested queue, or a system syncing after a network outage can cause `receivedAt` to differ from `occurredAt`. Using the receipt time instead of the occurrence time can distort reports.

`Instant` also does not prove that the source clock was accurate. In distributed systems, timestamps from different machines should not be treated as a perfect causal order; if deterministic ordering is required, add appropriate ordering rules or identifiers.

## 3. Future appointments: define what must be preserved

An appointment for “09:00 on June 1, 2030 in Berlin” has three core components: the local date and time, the `Europe/Berlin` zone, and a rule for handling cases where the clock time does not exist or occurs twice.

Converting it to an `Instant` enables scheduling execution or comparing against the current time. However, if only the `Instant` is kept and the original information is discarded, the system can lose the “09:00 in Berlin” intent when zone rules change.

Conversely, a broadcast locked to “start at exactly 07:00Z everywhere” can choose `Instant` as the authoritative data. When zone rules change, people in a given locality may see a different displayed local time; the start instant remains unchanged.

You must explicitly choose one of two primary contracts:

- **Preserve local time:** when zone rules change, recompute the instant from the local date-time and zone following an agreed process.
- **Preserve the fixed instant:** keep `Instant` unchanged; the displayed local time may change according to zone rules.

Do not infer this contract from the type name or from the fact that the data is “in the future”.

## 4. Why is a zone different from an offset?

A `ZoneOffset` such as `+02:00` is only an offset for a single interpretation. A `ZoneId` such as `Europe/Berlin` accesses a set of rules that can change by date and by time zone rule updates.

When resolving from an `Instant` to local time, the zone rules select an offset for that instant. When going from `LocalDateTime` to an instant, three cases can occur: one valid offset, no offset due to a forward clock jump (gap), or two offsets due to a backward clock shift (overlap).

Therefore, “09:00 +02:00” and “09:00 in Berlin” are not always equivalent representations. An appointment on a winter day may have a different offset. [ZonedDateTime](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/ZonedDateTime.html)

If the requested time falls in a gap or overlap, you can reject it, suggest another time, or require choosing an occurrence. What must be avoided is letting the default behavior of `atZone` inadvertently become an unapproved product policy.

## 5. Demonstration program: changing the view vs. rescheduling

The example below stores an occurred event and an appointment with local intent. The appointment is only auto-resolved when there is exactly one valid offset.

Save as `EventAndPlanDemo.java`:

```java
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.util.List;
import java.util.Objects;

public class EventAndPlanDemo {
    record ObservedEvent(Instant occurredAt, Instant receivedAt) {
        ObservedEvent {
            Objects.requireNonNull(occurredAt, "occurredAt");
            Objects.requireNonNull(receivedAt, "receivedAt");
        }
    }

    record Appointment(LocalDateTime localStart, ZoneId zone) {
        Appointment {
            Objects.requireNonNull(localStart, "localStart");
            Objects.requireNonNull(zone, "zone");
        }

        Instant resolve() {
            List<ZoneOffset> offsets = zone.getRules().getValidOffsets(localStart);
            if (offsets.size() != 1) {
                throw new IllegalArgumentException("Choose a policy for gap or overlap");
            }
            return ZonedDateTime.ofStrict(localStart, offsets.get(0), zone).toInstant();
        }
    }

    public static void main(String[] args) {
        ZoneId berlin = ZoneId.of("Europe/Berlin");
        ZoneId vietnam = ZoneId.of("Asia/Ho_Chi_Minh");
        ObservedEvent event = new ObservedEvent(
                Instant.parse("2025-06-01T07:00:00Z"),
                Instant.parse("2025-06-01T07:00:30Z"));

        System.out.println("eventBerlin=" + event.occurredAt().atZone(berlin));
        System.out.println("eventVietnam=" + event.occurredAt().atZone(vietnam));
        System.out.println("eventInstant=" + event.occurredAt());
        System.out.println("receiveDelaySeconds="
                + Duration.between(event.occurredAt(), event.receivedAt()).toSeconds());

        Appointment original = new Appointment(
                LocalDateTime.of(2030, 6, 1, 9, 0), berlin);
        Instant firstResolution = original.resolve();
        Appointment rescheduled = new Appointment(
                original.localStart().plusHours(1), original.zone());

        System.out.println("plannedInstant=" + firstResolution);
        System.out.println("rescheduledInstant=" + rescheduled.resolve());
        System.out.println("originalLocal=" + original.localStart());
        System.out.println("originalSnapshot=" + firstResolution);

        Instant fixedGlobalStart = Instant.parse("2030-06-01T07:00:00Z");
        System.out.println("globalBerlin=" + fixedGlobalStart.atZone(berlin));
        System.out.println("globalVietnam=" + fixedGlobalStart.atZone(vietnam));
    }
}
```

Compile and run with JDK 17 or later:

```shell
javac --release 17 EventAndPlanDemo.java
java EventAndPlanDemo
```

Stdout with IANA data where Berlin's summer rule is `+02:00` for the dates in the example:

```text
eventBerlin=2025-06-01T09:00+02:00[Europe/Berlin]
eventVietnam=2025-06-01T14:00+07:00[Asia/Ho_Chi_Minh]
eventInstant=2025-06-01T07:00:00Z
receiveDelaySeconds=30
plannedInstant=2030-06-01T07:00:00Z
rescheduledInstant=2030-06-01T08:00:00Z
originalLocal=2030-06-01T09:00
originalSnapshot=2030-06-01T07:00:00Z
globalBerlin=2030-06-01T09:00+02:00[Europe/Berlin]
globalVietnam=2030-06-01T14:00+07:00[Asia/Ho_Chi_Minh]
```

The two lines displaying the event do not create two different occurrences. Moving the appointment from 09:00 to 10:00 is what changes the intent and the planned instant. The `firstResolution` variable holds the initial resolution result; it does not automatically update when a new schedule record is created.

Checking `getValidOffsets` helps identify when a policy is needed. It does not choose a policy on behalf of the caller. [ZoneRules.getValidOffsets](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/zone/ZoneRules.html#getValidOffsets(java.time.LocalDateTime))

## 6. Time zone rule updates require a decision, not silent data mutation

Zone rules are subject to administrative decisions and can be updated. The same `LocalDateTime` and `ZoneId` may resolve differently when the rule set changes; future data is where this difference typically has scheduling impact.

Under a contract that preserves local time, you can review schedules that have not yet occurred, compute the new instant, and record the reschedule according to business workflows. Under a contract that preserves the instant, you must not change the instant just because new rules alter the displayed local time.

For events that have already occurred, do not recompute `occurredAt` from a local time using new rules and overwrite history. If you need to preserve exactly how the source interpreted the time, you can store the offset used, the source string, or rule version information.

`ZoneRulesProvider.getVersions(zoneId)` can report the versions provided by the provider, but storing only a version label does not guarantee that every future environment will still retain the old rule set. Requirements for exact reproduction need an appropriate data storage strategy. [ZoneRulesProvider](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/zone/ZoneRulesProvider.html)

## 7. Planned schedules and actual events need separate fields

An appointment has `plannedStart`, while when the customer arrives it may produce `actualStartedAt`; at the end, it has `actualEndedAt`. Actual timestamps do not necessarily match the planned schedule. Canceling an appointment also does not create an “occurred” event simply because the appointment date is in the past.

When rescheduling, distinguish the current schedule record from the change history. When correcting event data due to inaccurate source reporting, keep the original source and reason for correction according to auditability needs. These are business operations, distinct from changing the display time zone.

A recurring schedule is a rule that generates multiple appointment instances, not a single `Instant`. “Every Monday at 09:00 in Berlin” needs to retain the day of week, time of day, zone, and exception handling. Simply adding 168 hours from one appointment can cause the local time to drift across daylight saving time transitions.

## 8. Avoid models that lose meaning

- Storing only `LocalDateTime` for multi-zone events: insufficient data to identify a single point in time.
- Storing only today's offset for all future appointments: ignores date-dependent zone rules.
- Keeping only `Instant` for schedules that must preserve local time without storing the original intent.
- Keeping local time, zone, and instant together without specifying which field is authoritative when they conflict.
- Changing a schedule's status to “occurred” solely based on `scheduledAt < now`.

Not every model needs to store every field. Choose the original data, derived data, update policy, and clear field names. Names such as `occurredAt`, `receivedAt`, `scheduledLocal`, `scheduleZone`, and `resolvedStart` help avoid ambiguity better than a generic `time` field.

## 9. Self-practice

1. A payment is recorded in UTC and displayed in two zones: which field must remain unchanged?
2. A class is required to always start at 09:00 at its location: what needs to be stored besides the resolved instant?
3. An online session starts simultaneously worldwide: can `Instant` be used as the authoritative data even though it is in the future?
4. A device sends an event two minutes late: why should occurrence time and receipt time be separated?

Check: (1) the actual instant; (2) local date-time, zone, and policy; (3) yes, when the contract preserves the instant; (4) the two instants reflect two different occurrences and serve different analyses.